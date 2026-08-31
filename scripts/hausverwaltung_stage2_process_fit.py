import csv, json, os, re, unicodedata
SRC='data/hausverwaltung/size_agent_first/size_agent_first_final_2026-08-31.csv'
OUT='data/hausverwaltung/size_agent_first'

def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower().replace('&',' und ')
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

ADD={
'at home FM Services GmbH':'facility management / recurring building operations and back-office workflows',
'BOE Gebäudemanagement Gesellschaft m.b.H.':'commercial/technical property management, accounting, operating-cost allocation, contracts and tenant/owner workflows',
'CBRE GmbH':'large property/facility management platform with recurring real-estate back-office processes',
'GBG Gebäude- und Baumanagement Graz GmbH':'large building-management operator with technical and administrative property processes',
'International Campus Austria GmbH':'large student-housing operator with tenant, property and facility operations',
'McArthurGlen Management Gesellschaft m.b.H.':'shopping-centre management with tenant, service-charge, facility and operational workflows',
'Porsche Immobilien Gesellschaft m.b.H.':'large in-house real-estate/facility operator with maintenance, contractor and property administration processes',
'REIWAG Facility Services GmbH':'large facility/property services operator with recurring back-office and building processes',
'SES Center Management GmbH':'multi-site shopping-centre management with tenant, facility and commercial administration workflows',
'Supernova Invest GmbH':'active asset and centre management; commercial/technical management and tenant workflows',
'WSE Wiener Standortentwicklung GmbH':'explicitly develops, manages and administers real estate including office and public buildings',
'Bundesimmobiliengesellschaft m.b.H.':'large property operator with Hausverwaltung, tenant service, operating-cost accounting and maintenance workflows',
'ista Österreich GmbH':'high-volume billing, meter, operating-cost, customer and Hausverwaltung-facing workflows',
'Realverwaltung GmbH':'one of Austria’s larger commercial Hausverwaltungen; tenant and commercial/technical FM processes',
'STRABAG Property and Facility Services GmbH':'large property/facility management operation with recurring commercial and technical back-office',
'FLE GmbH':'licensed Immobilienverwalter with Immobilienmanagement and portfolio administration',
'GSA Wohnbauträger GmbH':'group provides property management, accounting, billing, complaints, document and contractor workflows',
'KIBB Immobilien GmbH':'explicit Hausverwaltung with billing, customer portal, legal/technical and tenant-owner workflows',
'VIVIR Holding GmbH':'licensed Immobilienverwalter; recurring real-estate administration qualifies for process-fit pool',
'Zurich Immobilien Liegenschaftsverwaltungs-GesmbH':'direct Liegenschaftsverwaltung entity with recurring administration workflows',
'AI Immobilienverwertung GmbH.':'WKO lists Mietshausverwaltung; recurring rental-house administration processes',
'CBRE GWS Austria GmbH':'large facility/property services operator with recurring property back-office',
'GRAWE Immo AG':'manages GRAWE real-estate portfolio across Austria and operates customer service',
'PFG Liegenschaftsbewirtschaftungs GmbH &Co KG':'Liegenschaftsbewirtschaftung is directly aligned with property administration workflows',
'PRISMA Zentrum für Standort- und Regionalentwicklung GmbH':'100+ buildings under management; commercial/technical Hausverwaltung, facility services, accounting and rent administration',
'Stadt Wien - Wiener Wohnen Kundenservice GmbH':'very large housing customer-service/property operation with rent and operating-cost accounting',
'Unibail-Rodamco Austria Verwaltungs GmbH':'large shopping-centre/property administration operator with tenant and facility workflows',
'ÖBB-Immobilienmanagement Gesellschaft mbH':'Austria-scale Hausverwaltung with commercial/technical management, tenant service and rent/operating-cost billing',
}
SECONDARY={
'APCOA Austria GmbH':'large parking operator with back-office/customer/billing automation potential, but not sufficiently close to Hausverwaltung workflows',
'Erste Group Immorent GmbH':'large real-estate finance/leasing platform; automation potential is strong but process set is less Hausverwaltung-like',
'UBM Development AG':'large developer with substantial administration, but recurring property-management processes are not the primary operation',
'Salinen Immobilien Gesellschaft m.b.H.':'internal/group real-estate entity; scale exists but recurring Hausverwaltung process depth not yet proven',
'Bank Austria Real Invest Asset Management GmbH':'real-estate asset/fund management; finance-heavy back office but less direct property administration',
'Reinberg & Partner Immobilienberatung GmbH':'real-estate advisory/consulting; automation potential exists but less recurring property operations',
'WEGRAZ Gesellschaft für Stadterneuerung und Assanierung m.b.H.':'development/urban-renewal operator; relevant administration but less direct Hausverwaltung workflow evidence',
'Wohnraumwerk Bauträger- und Projektentwicklungs GmbH':'developer/project company; relevant back office but not enough recurring property-management evidence',
'Oberbank Infrastruktur Management GmbH':'internal infrastructure/asset management; potentially relevant but process similarity is not yet established',
}
EXCLUDE={
'SEE.HAUS Weiden Betriebs GmbH':'operating business is hospitality/accommodation rather than property administration',
'Reischauer Consulting GmbH':'consulting-focused business rather than recurring property operations',
'U.M. Bau AG':'construction-focused business rather than recurring Hausverwaltung/property back-office',
}

def mkmap(d): return {norm(k):(k,v) for k,v in d.items()}
A,S,X=mkmap(ADD),mkmap(SECONDARY),mkmap(EXCLUDE)
rows=list(csv.DictReader(open(SRC,encoding='utf-8-sig',newline='')))
review=[]; main=[]; secondary=[]
for r in rows:
    cls=r.get('agent_class','')
    rn=norm(r.get('company_name',''))
    if r.get('sales_include')=='yes':
        r['process_fit_class']='PRIMARY_CORE'
        r['process_fit_reason']='existing agent-first core target'
        r['process_sales_include']='yes'
        main.append(r)
    elif cls=='E_ADJACENT_30_PLUS':
        if rn in A:
            dec='ADD_TO_SALES_POOL'; reason=A[rn][1]; r['process_sales_include']='yes'; main.append(r)
        elif rn in S:
            dec='SECONDARY_PROCESS_TARGET'; reason=S[rn][1]; r['process_sales_include']='secondary'; secondary.append(r)
        elif rn in X:
            dec='EXCLUDE_PROCESS_MISMATCH'; reason=X[rn][1]; r['process_sales_include']='no'
        else:
            dec='UNRESOLVED_PROCESS_REVIEW'; reason='adjacent row not explicitly reviewed'; r['process_sales_include']='review'
        r['process_fit_class']=dec; r['process_fit_reason']=reason
        review.append({
          'company_name':r.get('company_name',''),'previous_class':cls,'process_fit_class':dec,
          'process_fit_reason':reason,'website':r.get('website',''),'states_seen':r.get('states_seen','')})
    else:
        r['process_fit_class']='NOT_IN_PROCESS_REVIEW'; r['process_fit_reason']='not in prior core/adjacent pool'; r['process_sales_include']='no'

os.makedirs(OUT,exist_ok=True)
rf=['company_name','previous_class','process_fit_class','process_fit_reason','website','states_seen']
with open(f'{OUT}/adjacent_process_review_final_2026-08-31.tsv','w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rf,delimiter='\t'); w.writeheader(); w.writerows(review)
fields=list(rows[0].keys())
for extra in ['process_fit_class','process_fit_reason','process_sales_include']:
    if extra not in fields: fields.append(extra)
with open(f'{OUT}/sales_targets_process_fit_2026-08-31.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(main)
with open(f'{OUT}/secondary_process_targets_2026-08-31.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(secondary)
summary={
 'previous_core_targets':sum(1 for r in rows if r.get('sales_include')=='yes'),
 'adjacent_reviewed':len(review),
 'adjacent_added_to_main_sales_pool':sum(1 for r in review if r['process_fit_class']=='ADD_TO_SALES_POOL'),
 'secondary_process_targets':sum(1 for r in review if r['process_fit_class']=='SECONDARY_PROCESS_TARGET'),
 'process_mismatch_excluded':sum(1 for r in review if r['process_fit_class']=='EXCLUDE_PROCESS_MISMATCH'),
 'unresolved_process_review':sum(1 for r in review if r['process_fit_class']=='UNRESOLVED_PROCESS_REVIEW'),
 'main_process_fit_sales_pool':len(main),
 'main_plus_secondary_opportunities':len(main)+len(secondary),
 'stage2_definition':'size + sales process fit; includes classic Hausverwaltung and large property/facility/housing/centre operators with recurring administration, accounting, billing, tenant/customer, document, maintenance or contractor workflows',
 'stage3_started':False,
}
json.dump(summary,open(f'{OUT}/summary_process_fit_final_2026-08-31.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False,indent=2))