import importlib.util, os

HERE=os.path.dirname(__file__)
path=os.path.join(HERE,'hausverwaltung_size_external_search.py')
spec=importlib.util.spec_from_file_location('hv_size_base',path)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
# Breadth pass: employee query, career index, LinkedIn/Xing company-size snippets.
base.QUERY_FAMILIES=[x for x in base.QUERY_FAMILIES if x[0] in {'S01_EMPLOYEES','S05_CAREER','S06_LINKEDIN'}]
_orig_search=base.search
base.search=lambda q: _orig_search(q)[:4]
# Do not open result pages in breadth mode. Any 20+ signal is later deep-fetched/validated.
base.fetch_text=lambda url,cache: ('',url)
base.main()
