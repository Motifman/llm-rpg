"""
InMemoryDataStore - すべてのインメモリリポジトリで共有されるデータストレージ
"""
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta

# 必要なドメインオブジェクトのインポート
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.entity.sns_user import SnsUser
from ai_rpg_world.domain.sns.value_object.user_profile import UserProfile
from ai_rpg_world.domain.sns.value_object.follow import FollowRelationShip
from ai_rpg_world.domain.sns.value_object.block import BlockRelationShip
from ai_rpg_world.domain.sns.value_object.subscribe import SubscribeRelationShip
from ai_rpg_world.domain.sns.value_object.user_id import UserId as SnsUserId
from ai_rpg_world.domain.sns.value_object.post_id import PostId
from ai_rpg_world.domain.sns.value_object.post_content import PostContent
from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.enum.sns_enum import PostVisibility
from ai_rpg_world.domain.sns.value_object.reply_id import ReplyId
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.entity.notification import Notification as SnsNotification
from ai_rpg_world.domain.sns.value_object.notification_id import NotificationId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId


class InMemoryDataStore:
    """インメモリリポジトリ用の共有データストア"""

    def __init__(self):
        # SNS Domain
        self.sns_users: Dict[SnsUserId, UserAggregate] = {}
        self.sns_username_to_user_id: Dict[str, SnsUserId] = {}
        self.sns_next_user_id = 1
        
        self.posts: Dict[PostId, PostAggregate] = {}
        self.next_post_id = 1
        
        self.replies: Dict[ReplyId, ReplyAggregate] = {}
        self.next_reply_id = 1
        
        self.sns_notifications: Dict[NotificationId, SnsNotification] = {}
        self.next_sns_notification_id = 1
        
        # Player Domain (TBD: リファクタリング後の集約に合わせる)
        self.players: Dict[Any, Any] = {}
        self.player_profiles: Dict[PlayerId, Any] = {}
        self.player_inventories: Dict[PlayerId, Any] = {}
        self.player_statuses: Dict[PlayerId, Any] = {}
        self.next_player_id = 1
        
        # Trade Domain
        self.trades: Dict[Any, Any] = {}
        self.next_trade_id = 1

        # Quest Domain
        self.quests: Dict[QuestId, QuestAggregate] = {}
        self.next_quest_id = 1

        # Guild Domain
        self.guilds: Dict[GuildId, GuildAggregate] = {}
        self.next_guild_id = 1

        # Item Domain
        self.items: Dict[ItemInstanceId, ItemAggregate] = {}
        self.next_item_instance_id = 1
        
        # World Domain
        self.physical_maps: Dict[SpotId, PhysicalMapAggregate] = {}
        self.weather_zones: Dict[WeatherZoneId, WeatherZone] = {}
        self.monsters: Dict[MonsterId, MonsterAggregate] = {}
        self.world_object_to_monster_id: Dict[WorldObjectId, MonsterId] = {}
        self.next_monster_id = 1
        self.next_world_object_id = 100000  # NPC用。プレイヤーIDと衝突しない範囲
        self.spawn_tables: Dict[SpotId, SpotSpawnTable] = {}
        self.hit_boxes: Dict[HitBoxId, HitBoxAggregate] = {}
        self.next_hit_box_id = 1
        self.world_maps: Dict[Any, Any] = {} # Dict[WorldId, WorldMapAggregate]
        self.spot_to_world_id: Dict[SpotId, Any] = {} # Dict[SpotId, WorldId]
        
        # サンプルデータの投入
        self._setup_sample_data()

    def _setup_sample_data(self):
        """全てのドメインのサンプルデータをセットアップ"""
        self._setup_sns_users()
        self._setup_sns_posts()
        self._setup_sns_replies()

    def _setup_sns_users(self):
        """SNSユーザーのサンプルデータ"""
        # ユーザー1: 勇者
        u1_profile = UserProfile("hero_user", "勇者", "世界を救う勇者です")
        u1_user = SnsUser(SnsUserId(1), u1_profile)
        u1_follows = [FollowRelationShip(SnsUserId(1), SnsUserId(2)), FollowRelationShip(SnsUserId(1), SnsUserId(3))]
        u1_subscribes = [SubscribeRelationShip(SnsUserId(1), SnsUserId(2))]
        u1_agg = UserAggregate(SnsUserId(1), u1_user, u1_follows, [], u1_subscribes)
        self.sns_users[SnsUserId(1)] = u1_agg
        self.sns_username_to_user_id["hero_user"] = SnsUserId(1)

        # ユーザー2: 魔法使い
        u2_profile = UserProfile("mage_user", "魔法使い", "魔法の研究に没頭しています")
        u2_user = SnsUser(SnsUserId(2), u2_profile)
        u2_follows = [FollowRelationShip(SnsUserId(2), SnsUserId(1)), FollowRelationShip(SnsUserId(2), SnsUserId(3))]
        u2_blocks = [BlockRelationShip(SnsUserId(2), SnsUserId(4))]
        u2_subscribes = [SubscribeRelationShip(SnsUserId(2), SnsUserId(1))]
        u2_agg = UserAggregate(SnsUserId(2), u2_user, u2_follows, u2_blocks, u2_subscribes)
        self.sns_users[SnsUserId(2)] = u2_agg
        self.sns_username_to_user_id["mage_user"] = SnsUserId(2)

        # ユーザー3: 戦士
        u3_profile = UserProfile("warrior_user", "戦士", "剣の修行に励んでいます")
        u3_user = SnsUser(SnsUserId(3), u3_profile)
        u3_agg = UserAggregate(SnsUserId(3), u3_user, [FollowRelationShip(SnsUserId(3), SnsUserId(1))], [], [])
        self.sns_users[SnsUserId(3)] = u3_agg
        self.sns_username_to_user_id["warrior_user"] = SnsUserId(3)

        # ユーザー4: 盗賊
        u4_profile = UserProfile("thief_user", "盗賊", "宝探しが趣味です")
        u4_user = SnsUser(SnsUserId(4), u4_profile)
        u4_agg = UserAggregate(SnsUserId(4), u4_user, [FollowRelationShip(SnsUserId(4), SnsUserId(1))], [], [])
        self.sns_users[SnsUserId(4)] = u4_agg
        self.sns_username_to_user_id["thief_user"] = SnsUserId(4)

        # ユーザー5: 僧侶
        u5_profile = UserProfile("priest_user", "僧侶", "人々を癒すのが使命です")
        u5_user = SnsUser(SnsUserId(5), u5_profile)
        u5_follows = [FollowRelationShip(SnsUserId(5), SnsUserId(1)), FollowRelationShip(SnsUserId(5), SnsUserId(2))]
        u5_subscribes = [SubscribeRelationShip(SnsUserId(5), SnsUserId(1))]
        u5_agg = UserAggregate(SnsUserId(5), u5_user, u5_follows, [], u5_subscribes)
        self.sns_users[SnsUserId(5)] = u5_agg
        self.sns_username_to_user_id["priest_user"] = SnsUserId(5)

        # ユーザー6: 商人
        u6_profile = UserProfile("merchant_user", "商人", "良い取引を探しています")
        u6_user = SnsUser(SnsUserId(6), u6_profile)
        u6_blocks = [BlockRelationShip(SnsUserId(6), SnsUserId(1))]
        u6_agg = UserAggregate(SnsUserId(6), u6_user, [], u6_blocks, [])
        self.sns_users[SnsUserId(6)] = u6_agg
        self.sns_username_to_user_id["merchant_user"] = SnsUserId(6)

        self.sns_next_user_id = 7

    def _setup_sns_posts(self):
        """SNSポストのサンプルデータ"""
        base_time = datetime.now()
        
        posts_data = [
            (1, 1, "今日は新しい冒険が始まる！ みんなの応援待ってるよ！", ["冒険", "勇者"], PostVisibility.PUBLIC, 120),
            (2, 2, "新しい魔法の研究中！ 魔法の力で世界をより良くしたいな。", ["魔法", "研究"], PostVisibility.PUBLIC, 90),
            (3, 3, "今日も剣の修行を頑張った！ 強くなるために毎日努力だ。", ["剣術", "修行"], PostVisibility.FOLLOWERS_ONLY, 60),
            (4, 4, "素晴らしい宝物を見つけたぞ！ これでみんな幸せになるね。", ["宝物", "冒険"], PostVisibility.PUBLIC, 45),
            (5, 5, "今日も多くの人々を癒すことができた。 みんなの笑顔を見るのが何よりの喜びだ。", ["癒し", "僧侶"], PostVisibility.PUBLIC, 30),
            (6, 6, "良い品物を手に入れたよ！ 興味のある人は声かけてね。", ["取引", "商人"], PostVisibility.FOLLOWERS_ONLY, 15),
            (7, 1, "もちろん一緒に研究しよう！ 魔法の力は冒険に欠かせないよ。", ["魔法", "協力"], PostVisibility.PUBLIC, 10),
            (8, 2, "みんなの応援ありがとう！ 一緒に素晴らしい冒険にしよう。", ["魔法", "冒険"], PostVisibility.PUBLIC, 5),
            (9, 1, "今日の出来事について考えている。冒険は楽しいけれど、責任も重いな...", ["メモ", "内省"], PostVisibility.PRIVATE, 3),
            (10, 2, "新しい魔法の理論をまとめている。フォロワー諸君の意見が聞きたい。", ["魔法", "理論", "研究"], PostVisibility.FOLLOWERS_ONLY, 2),
            (11, 3, "剣の修行は厳しいが、強くなれている実感がある。明日はもっと頑張ろう。", ["日記", "修行"], PostVisibility.PRIVATE, 1),
            (12, 1, "明日、街の広場で大きなイベントが開催されます！ みんなで一緒に楽しみましょう！", ["イベント", "街", "みんな"], PostVisibility.PUBLIC, 180),
            (13, 2, "新しい魔法の研究成果を発表します！ 火の魔法が大幅にパワーアップしました。", ["魔法", "研究", "進化"], PostVisibility.PUBLIC, 150),
            (14, 4, "昔の冒険の思い出を語ろう。ドラゴンと戦ったあの日は忘れられないな。", ["冒険", "思い出", "ドラゴン"], PostVisibility.PUBLIC, 105),
            (15, 5, "今夜、癒しの音楽会を開催します。美しい音楽と共に心を癒しましょう。", ["音楽", "癒し", "イベント"], PostVisibility.PUBLIC, 75),
            (16, 3, "新しい剣術の技を開発しました！ フォロワー諸君に特別に公開します。", ["剣術", "技", "修行"], PostVisibility.FOLLOWERS_ONLY, 45),
            (17, 4, "次の宝探しのヒント：森の奥深く、月の光が差す場所を探せ。", ["宝探し", "ヒント", "冒険"], PostVisibility.PUBLIC, 30),
            (18, 6, "スペシャルオファー！ 今日だけ、全商品20%オフ！ お買い得ですよ。", ["セール", "商人", "お得"], PostVisibility.PUBLIC, 20),
            (19, 2, "魔法のワークショップ開催！ 初心者でも参加OKです。一緒に魔法を学びましょう。", ["ワークショップ", "魔法", "初心者"], PostVisibility.PUBLIC, 10),
            (20, 1, "ついに魔王を倒した！ みんなの応援のおかげだ。ありがとう！", ["勝利", "英雄", "魔王"], PostVisibility.PUBLIC, 240),
        ]

        for pid, uid, content, tags, visibility, mins_ago in posts_data:
            post_content = PostContent(content=content, hashtags=tuple(tags), visibility=visibility)
            created_at = base_time - timedelta(minutes=mins_ago)
            post = PostAggregate(PostId(pid), SnsUserId(uid), post_content, set(), set(), set(), False, None, None, created_at)
            self.posts[PostId(pid)] = post
            
        # いいねの追加
        self.posts[PostId(1)].like_post(SnsUserId(2))
        self.posts[PostId(1)].like_post(SnsUserId(3))
        self.posts[PostId(1)].like_post(SnsUserId(5))
        self.posts[PostId(2)].like_post(SnsUserId(1))
        self.posts[PostId(2)].like_post(SnsUserId(5))
        self.posts[PostId(3)].like_post(SnsUserId(1))
        self.posts[PostId(3)].like_post(SnsUserId(2))
        self.posts[PostId(4)].like_post(SnsUserId(1))
        self.posts[PostId(5)].like_post(SnsUserId(1))
        self.posts[PostId(5)].like_post(SnsUserId(2))
        self.posts[PostId(5)].like_post(SnsUserId(3))
        self.posts[PostId(5)].like_post(SnsUserId(4))
        self.posts[PostId(6)].like_post(SnsUserId(4))
        self.posts[PostId(7)].like_post(SnsUserId(2))
        self.posts[PostId(8)].like_post(SnsUserId(1))
        self.posts[PostId(8)].like_post(SnsUserId(3))
        self.posts[PostId(8)].like_post(SnsUserId(5))
        self.posts[PostId(10)].like_post(SnsUserId(1))
        for uid in [1, 2, 3, 4, 5, 6]:
            self.posts[PostId(12)].like_post(SnsUserId(uid))
        self.posts[PostId(13)].like_post(SnsUserId(1))
        self.posts[PostId(13)].like_post(SnsUserId(3))
        self.posts[PostId(13)].like_post(SnsUserId(5))
        self.posts[PostId(14)].like_post(SnsUserId(1))
        self.posts[PostId(14)].like_post(SnsUserId(2))
        self.posts[PostId(15)].like_post(SnsUserId(1))
        self.posts[PostId(15)].like_post(SnsUserId(2))
        self.posts[PostId(15)].like_post(SnsUserId(4))
        self.posts[PostId(15)].like_post(SnsUserId(6))
        self.posts[PostId(16)].like_post(SnsUserId(1))
        self.posts[PostId(16)].like_post(SnsUserId(2))
        self.posts[PostId(17)].like_post(SnsUserId(1))
        self.posts[PostId(17)].like_post(SnsUserId(6))
        for uid in [1, 2, 3, 4, 5]:
            self.posts[PostId(18)].like_post(SnsUserId(uid))
        for uid in [1, 3, 4, 5, 6]:
            self.posts[PostId(19)].like_post(SnsUserId(uid))
        for uid in range(1, 7):
            self.posts[PostId(20)].like_post(SnsUserId(uid))

        self.next_post_id = 21

    def _setup_sns_replies(self):
        """SNSリプライのサンプルデータ"""
        base_time = datetime.now()
        
        replies_data = [
            (1, 2, "一緒に冒険に行きたい！ 僕も手伝うよ。", ["冒険", "協力"], PostId(1), None, 105),
            (2, 3, "素晴らしい冒険の始まりですね！ 応援しています。", ["冒険", "応援"], PostId(1), None, 90),
            (3, 1, "その魔法、私も興味あるよ！ 一緒に研究しよう。", ["魔法", "研究"], PostId(2), None, 2700),
            (4, 2, "いいね！ 魔法の理論について議論しよう。", ["魔法", "議論"], None, ReplyId(3), 1800),
            (5, 1, "その宝物、すごく魅力的だね！ 見に行きたい。", ["宝物", "冒険"], PostId(4), None, 40),
            (6, 4, "いつもみんなを癒してくれるなんて、素晴らしいですね。", ["癒し", "感謝"], PostId(5), None, 25),
            (7, 5, "ありがとう！ みんなの笑顔が私の原動力だよ。", ["癒し", "感謝"], None, ReplyId(6), 20),
            (8, 3, "そんな気持ち、素晴らしいと思います！", ["癒し", "感動"], None, ReplyId(7), 15),
            (9, 1, "良い品物があるんですね。興味ありますよ。", ["取引", "興味"], PostId(6), None, 10),
            (10, 4, "冒険の詳細、聞かせてほしいな！", ["冒険", "詳細"], PostId(1), None, 5),
        ]

        for rid, uid, content, tags, pid, parent_rid, mins_ago in replies_data:
            rep_content = PostContent(content=content, hashtags=tuple(tags), visibility=PostVisibility.PUBLIC)
            created_at = base_time - timedelta(minutes=mins_ago)
            reply = ReplyAggregate(ReplyId(rid), SnsUserId(uid), rep_content, set(), set(), set(), False, pid, parent_rid, created_at)
            self.replies[ReplyId(rid)] = reply
            
        self.next_reply_id = 11

    def clear_all(self):
        """全てのデータをクリア"""
        self.sns_users.clear()
        self.sns_username_to_user_id.clear()
        self.sns_next_user_id = 1
        self.posts.clear()
        self.next_post_id = 1
        self.replies.clear()
        self.next_reply_id = 1
        self.sns_notifications.clear()
        self.next_sns_notification_id = 1
        self.players.clear()
        self.next_player_id = 1
        self.player_profiles.clear()
        self.player_inventories.clear()
        self.player_statuses.clear()
        self.trades.clear()
        self.next_trade_id = 1
        self.quests.clear()
        self.next_quest_id = 1
        self.guilds.clear()
        self.next_guild_id = 1
        self.items.clear()
        self.next_item_instance_id = 1
        self.physical_maps.clear()
        self.weather_zones.clear()
        self.monsters.clear()
        self.world_object_to_monster_id.clear()
        self.next_monster_id = 1
        self.next_world_object_id = 100000
        self.spawn_tables.clear()
        self.hit_boxes.clear()
        self.world_maps.clear()
        self.spot_to_world_id.clear()

    def take_snapshot(self) -> Dict[str, Any]:
        """現在のデータのスナップショットを作成する"""
        import copy
        return {
            "player_statuses": copy.deepcopy(self.player_statuses),
            "physical_maps": copy.deepcopy(self.physical_maps),
            "weather_zones": copy.deepcopy(self.weather_zones),
            "monsters": copy.deepcopy(self.monsters),
            "world_object_to_monster_id": copy.deepcopy(self.world_object_to_monster_id),
            "spawn_tables": copy.deepcopy(self.spawn_tables),
            "hit_boxes": copy.deepcopy(self.hit_boxes),
            "player_inventories": copy.deepcopy(self.player_inventories),
            "trades": copy.deepcopy(self.trades),
            "quests": copy.deepcopy(self.quests),
            "guilds": copy.deepcopy(self.guilds),
            "items": copy.deepcopy(self.items),
            "sns_users": copy.deepcopy(self.sns_users),
            "posts": copy.deepcopy(self.posts),
            "replies": copy.deepcopy(self.replies),
        }

    def restore_snapshot(self, snapshot: Dict[str, Any]):
        """スナップショットからデータを復元する"""
        self.player_statuses = snapshot["player_statuses"]
        self.physical_maps = snapshot["physical_maps"]
        self.weather_zones = snapshot["weather_zones"]
        self.monsters = snapshot["monsters"]
        self.world_object_to_monster_id = snapshot["world_object_to_monster_id"]
        self.spawn_tables = snapshot.get("spawn_tables", {})
        self.hit_boxes = snapshot["hit_boxes"]
        self.player_inventories = snapshot["player_inventories"]
        self.trades = snapshot["trades"]
        self.quests = snapshot.get("quests", {})
        self.guilds = snapshot.get("guilds", {})
        self.items = snapshot["items"]
        self.sns_users = snapshot["sns_users"]
        self.posts = snapshot["posts"]
        self.replies = snapshot["replies"]
