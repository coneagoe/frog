SSF_HOLDER_KEYWORDS = (
    "全国社保基金",
    "社保基金",
    "基本养老保险基金",
)


def is_social_security_holder(holder_name: object) -> bool:
    if holder_name is None:
        return False
    if isinstance(holder_name, float) and holder_name != holder_name:
        return False
    normalized = str(holder_name).strip()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in SSF_HOLDER_KEYWORDS)
