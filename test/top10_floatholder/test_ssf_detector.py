from top10_floatholder.ssf_detector import is_social_security_holder


def test_is_social_security_holder_matches_ssf_keywords():
    assert is_social_security_holder("全国社保基金一一八组合") is True
    assert is_social_security_holder("基本养老保险基金八零二组合") is True


def test_is_social_security_holder_rejects_non_ssf_names():
    assert is_social_security_holder("香港中央结算有限公司") is False
    assert is_social_security_holder("招商银行股份有限公司") is False


def test_is_social_security_holder_rejects_nan_names():
    assert is_social_security_holder(float("nan")) is False
