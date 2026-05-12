"""URL 规范化工具 - 用于去重前的 URL 标准化。"""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# 需要移除的追踪参数
_TRACKING_PARAMS = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_cid",
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "msclkid",
    "twclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "ref_url",
    "_ga",
    "_gl",
    "yclid",
    "zanpid",
    "hsa_cam",
    "hsa_grp",
    "hsa_mt",
    "hsa_src",
    "hsa_ad",
    "hsa_acc",
    "hsa_net",
    "hsa_ver",
    "hsa_kw",
    "hsa_tgt",
    "hsa_la",
    "hsa_ol",
})


def normalize_url(url: str) -> str:
    """
    规范化 URL 用于去重比较。

    规则：
    - scheme/domain 转小写
    - 移除 fragment
    - 移除追踪参数 (utm_*, fbclid, gclid 等)
    - 保留有意义的 query 参数
    - 去掉末尾斜杠（非根路径）
    - query 参数按 key 排序保证稳定性
    """
    parsed = urlparse(url.strip())

    # scheme + netloc 小写
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # 去掉末尾斜杠（非根路径）
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # 过滤追踪参数，保留有意义参数
    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered_params: dict[str, list[str]] = {}
    for key, values in query_params.items():
        if key.lower() not in _TRACKING_PARAMS:
            filtered_params[key] = values

    # 排序保证稳定性
    sorted_query = urlencode(sorted(filtered_params.items()), doseq=True) if filtered_params else ""

    # 去掉 fragment
    normalized = urlunparse((scheme, netloc, path, "", sorted_query, ""))
    return normalized


def extract_domain(url: str) -> str:
    """提取域名（小写）。"""
    return urlparse(url).netloc.lower()


def is_valid_url(url: str) -> bool:
    """检查是否为有效 HTTP(S) URL。"""
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False
