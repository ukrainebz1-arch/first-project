import importlib.util, os

HERE=os.path.dirname(__file__)
path=os.path.join(HERE,'hausverwaltung_size_external_search.py')
spec=importlib.util.spec_from_file_location('hv_size_base',path)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

_orig_read=base.read_csv
def canonical_read(p):
    if p.endswith('data/wko-immobilienverwalter/wko_immobilienverwalter_austria_unique.csv'):
        rows=_orig_read('data/hausverwaltung/size_strict_v2/size_screening_strict_v2.csv')
        rows=sorted(rows,key=lambda r:(base.clean(r.get('company_name','')).casefold(),r.get('canonical_key','')))
        return [{'company_name':r.get('company_name',''),'firmaid':r.get('firmaids','')} for r in rows]
    return _orig_read(p)
base.read_csv=canonical_read

# High-recall but bounded first probe: exact employee query + Hausverwaltung-specific employee query.
base.QUERY_FAMILIES=[x for x in base.QUERY_FAMILIES if x[0] in {'S01_EMPLOYEES','S03_HAUSVERWALTUNG'}]
_orig_search=base.search
base.search=lambda q: _orig_search(q)[:3]
base.main()
