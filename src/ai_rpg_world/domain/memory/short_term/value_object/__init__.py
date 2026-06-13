# NOTE: 意図的に空にする (Issue #470 Phase 1)。
#
# Value Object は必ず concrete file から import すること:
#     from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import L4MidSummary
#
# 集約的 re-export (`from ai_rpg_world.domain.memory.short_term.value_object import L4MidSummary`)
# は避ける — Phase 1 の方針として「import path から VO の出処が一目で分かる」を優先。
