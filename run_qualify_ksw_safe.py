import qualify_ksw_groups as q

_original_urljoin = q.urljoin

def safe_urljoin(base, url):
    try:
        return _original_urljoin(base, url)
    except (ValueError, TypeError):
        return base

q.urljoin = safe_urljoin
q.main()
