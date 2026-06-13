"""Settings 衍生屬性：白名單解析與 LINE 啟用判斷。

webhook 測試注入的是已經是 list 的假 settings，所以真正的逗號解析從沒被跑到——
這裡直接對 Settings 測，盯住兩個安全相關的邊界：空字串不可變成「鎖死所有人」、
去空白要正確。
"""

from app.config import Settings


def test_allowed_user_ids_splits_and_strips():
    s = Settings(line_allowed_user_ids="Ua, Ub , Uc")
    assert s.line_allowed_user_id_list == ["Ua", "Ub", "Uc"]


def test_allowed_user_ids_empty_means_no_restriction():
    # 空字串必須是「不限制」(空 list)，不能變成 [""]——否則白名單看似非空、反而擋掉所有人。
    assert Settings(line_allowed_user_ids="").line_allowed_user_id_list == []
    # 只有逗號/空白也一樣視為未設定
    assert Settings(line_allowed_user_ids=" , ").line_allowed_user_id_list == []


def test_line_enabled_requires_both_secret_and_token():
    assert Settings(line_channel_secret="s", line_channel_access_token="t").line_enabled is True
    # 只填一半 → 視為未啟用（fail closed）
    assert Settings(line_channel_secret="s", line_channel_access_token="").line_enabled is False
    assert Settings(line_channel_secret="", line_channel_access_token="t").line_enabled is False
