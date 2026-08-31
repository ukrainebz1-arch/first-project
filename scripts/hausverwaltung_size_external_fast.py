import importlib.util, os

HERE=os.path.dirname(__file__)
path=os.path.join(HERE,'hausverwaltung_size_external_search.py')
spec=importlib.util.spec_from_file_location('hv_size_base',path)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
# First-pass breadth: strongest generic query + career + business-social company-size snippets.
base.QUERY_FAMILIES=[x for x in base.QUERY_FAMILIES if x[0] in {'S01_EMPLOYEES','S05_CAREER','S06_LINKEDIN'}]
# Keep the first pass broad but cheap; deeper S02/S03/S04 queries are reserved for unresolved companies.
_orig_search=base.search
base.search=lambda q: _orig_search(q)[:3]
base.main()
