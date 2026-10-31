"""Being のうち、まだ ``ai_rpg_world.being`` へ移していない部品 (#1469)。

Being 集約、人柄 (``Persona``)、``BeingId``、所属 (``BeingAttachment``) は ``ai_rpg_world.being.domain`` にある。ここに
残るのは例外・snapshot・codec・リポジトリのインタフェースで、移し替えの PR ごとに減らす。
"""
