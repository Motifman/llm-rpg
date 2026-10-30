"""既存のSNS集約を、公開限定の単一CommandScopeで確定する。"""

from __future__ import annotations

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactoryPort
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.common.execution_provenance import current_execution_provenance
from ai_rpg_world.application.social.public_sns.access_policy import MAX_PUBLIC_SNS_ANCESTORS, PublicSnsAccessPolicy
from ai_rpg_world.application.social.public_sns.command_repository import PublicSnsCommandRepositories
from ai_rpg_world.application.social.public_sns.contracts import (
    ContentKind,
    PublicSnsContentDto,
    PublicSnsInvalidRequestError,
    PublicSnsUnavailableError,
)
from ai_rpg_world.application.social.public_sns.notification_delivery import (
    PublicSnsAfterCommitHandoff,
    PublicSnsIncomingNotificationService,
)
from ai_rpg_world.application.social.public_sns.notification_events import PublicSnsActivityEvent
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.exception import SnsDomainException
from ai_rpg_world.domain.sns.value_object.post_content import PostContent
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.value_object.user_id import UserId


class PublicSnsCommandService:
    """投稿、親の返信数、通知を一度に確定し、旧SNSコマンドを経由しない。"""

    def __init__(
        self,
        scope_factory: CommandScopeFactoryPort[PublicSnsCommandRepositories],
        *,
        notification_handoff: PublicSnsAfterCommitHandoff | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._notification_handoff = notification_handoff

    def record_activity(self, event: PublicSnsActivityEvent) -> None:
        PublicSnsIncomingNotificationService(self._scope_factory).record_activity(event)

    def record_event(self, event: DomainEvent) -> None:
        from ai_rpg_world.application.social.public_sns.incoming_event_adapter import activity_from_domain_event

        with self._scope_factory.create() as context:
            activity = activity_from_domain_event(event, context.repositories.read.namespace)
            if activity is not None:
                context.collect(activity)

    def retry_pending_notifications(self, *, limit: int = 100) -> int:
        return self._notification_handoff.retry_pending(limit=limit) if self._notification_handoff else 0

    def publish(self, viewer_user_id: int, content: str, target_id: str | None = None) -> PublicSnsContentDto:
        if not isinstance(content, str) or not content.strip() or len(content) > 280:
            raise PublicSnsInvalidRequestError("本文は1から280文字で入力してください")
        try:
            body = PostContent.create(content)
        except SnsDomainException as error:
            raise PublicSnsInvalidRequestError(str(error)) from error
        result: PublicSnsContentDto | None = None
        try:
            with self._scope_factory.create() as context:
                repos = context.repositories
                actor = repos.users.find_by_id(UserId(viewer_user_id))
                if actor is None:
                    raise PublicSnsUnavailableError()
                access = PublicSnsAccessPolicy(repos.read)
                parent = access.require_visible_target(viewer_user_id, target_id) if target_id is not None else None
                if parent is not None:
                    chain = access.visible_chain(viewer_user_id, parent)
                    if chain is None or len(chain) >= MAX_PUBLIC_SNS_ANCESTORS:
                        raise PublicSnsUnavailableError()
                recipients: dict[int, str] = {}
                # 表示名は重複し得るため、@は一意なアカウント名だけに解決する。
                for name in sorted(PostContent.extract_mention_display_names(content)):
                    mentioned = repos.users.find_by_user_name(name)
                    if mentioned is not None and mentioned.profile.user_name == name:
                        recipients[mentioned.user_id.value] = "mention"
                aggregate: PostAggregate | ReplyAggregate
                kind: ContentKind
                if parent is None:
                    aggregate = PostAggregate.create(
                        repos.posts.generate_post_id(),
                        actor.user_id,
                        body,
                        author_display_name=actor.profile.display_name,
                        author_identity_token=actor.identity_token,
                    )
                    repos.posts.save(aggregate)
                    kind = "post"
                else:
                    aggregate = ReplyAggregate.create(
                        reply_id=repos.replies.generate_reply_id(),
                        parent_post_id=PostId(parent.local_id) if parent.kind == "post" else None,
                        parent_reply_id=ReplyId(parent.local_id) if parent.kind == "reply" else None,
                        parent_author_id=UserId(parent.author_user_id),
                        author_user_id=actor.user_id,
                        content=body,
                        author_display_name=actor.profile.display_name,
                        author_identity_token=actor.identity_token,
                        parent_identity_token=parent.identity_token,
                    )
                    repos.replies.save(aggregate)
                    if parent.kind == "post":
                        parent_post = repos.posts.find_by_id(PostId(parent.local_id))
                        if parent_post is None:
                            raise PublicSnsUnavailableError()
                        parent_post.add_reply(aggregate.reply_id)
                        repos.posts.save(parent_post)
                    else:
                        parent_reply = repos.replies.find_by_id(ReplyId(parent.local_id))
                        if parent_reply is None:
                            raise PublicSnsUnavailableError()
                        parent_reply.add_reply(aggregate.reply_id)
                        repos.replies.save(parent_reply)
                    # 同じ相手への返信とメンションは返信一件にまとめる。
                    recipients[parent.author_user_id] = "reply"
                    kind = "reply"
                public_id = f"sns:{repos.read.namespace}:{kind}:{aggregate.identity_token}"
                result = PublicSnsContentDto(
                    target_id=public_id,
                    kind=kind,
                    author_display_name=actor.profile.display_name,
                    author_target_id=f"sns:{repos.read.namespace}:user:{actor.identity_token}",
                    content=content,
                    created_at=aggregate.created_at,
                    parent_target_id=target_id,
                )
                bound_recipients = []
                for recipient_id, notification_kind in sorted(recipients.items()):
                    if recipient_id == viewer_user_id:
                        continue
                    recipient = repos.users.find_by_id(UserId(recipient_id))
                    if recipient is not None:
                        bound_recipients.append((recipient_id, recipient.identity_token, notification_kind))
                context.collect(
                    PublicSnsActivityEvent.create(
                        aggregate_id=public_id,
                        aggregate_type="PublicSnsActivity",
                        actor_user_id=viewer_user_id,
                        actor_identity_token=actor.identity_token,
                        target_id=public_id,
                        recipients=tuple(bound_recipients),
                        provenance=current_execution_provenance(),
                    )
                )
        except CommandPostCommitException as error:
            # 確定済み投稿を再実行させないため、境界の成功応答に必要な結果を残す。
            setattr(error, "result", result)
            raise
        assert result is not None
        return result
