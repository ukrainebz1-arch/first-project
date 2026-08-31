# Spedition Decision-Maker Contact Enrichment — Final

- Target companies: 118
- Primary decision makers: 242
- Final statuses: A_PUBLIC_MOBILE=11, B_DIRECT_PHONE=39, C_DIRECT_EMAIL_ONLY=21, D_NAMED_MANAGEMENT_LINE=3, E_CENTRAL_FALLBACK=163, F_NO_PUBLIC_DIRECT_CONTACT_FOUND=5
- Priority: public personal mobile > direct extension/named direct > verified personal business e-mail > named management line > central fallback.
- Shared phone numbers attached to multiple decision makers are downgraded and are not treated as direct.
- Guessed e-mail patterns are never marked verified without an independent public source.
- Historical public contacts are retained with age-adjusted confidence only when the person is independently confirmed as still relevant.
- Raw official crawl is preserved in official_hits.csv / official_chunks. all_contact_evidence.csv adds normalized provenance and validation state.

## Method performance (top by valid direct evidence)

- 02_TEAM_MANAGEMENT Team / Management / Geschäftsführung: valid_direct_hits=40, mobiles=3, direct_phones=16, personal_emails=19
- 20_PARTNER_GROUP Supplier / partner / group / case-study page: valid_direct_hits=23, mobiles=3, direct_phones=9, personal_emails=11
- 01_OFFICIAL_CONTACT Official Contact / official website: valid_direct_hits=22, mobiles=1, direct_phones=6, personal_emails=12
- 04_PRESS_NEWS Presse / News / Media: valid_direct_hits=6, mobiles=0, direct_phones=4, personal_emails=1
- 08_CAREER_CONTACT Karriere / Ansprechpartner: valid_direct_hits=5, mobiles=1, direct_phones=2, personal_emails=2
- 10_ARCHIVED_JOB Old / closed job ad: valid_direct_hits=5, mobiles=0, direct_phones=2, personal_emails=3
- 13_INDUSTRY_ASSOCIATION Industry association / membership: valid_direct_hits=5, mobiles=0, direct_phones=2, personal_emails=3
- 19_INDUSTRY_REGISTER Industry / transport / security register: valid_direct_hits=4, mobiles=2, direct_phones=0, personal_emails=2
- 11_WKO_PROFILE WKO Firmen A-Z: valid_direct_hits=4, mobiles=1, direct_phones=0, personal_emails=3
- 07_BROCHURE_PRESENTATION Brochure / Presentation / Fact Sheet: valid_direct_hits=4, mobiles=0, direct_phones=2, personal_emails=2

## Files

- final_contacts.csv — one row per primary decision maker; no blank status.
- all_contact_evidence.csv — normalized raw + curated evidence with provenance.
- method_performance.csv — channel effectiveness statistics and denominator notes.
- final_status_summary.csv — A–F status counts.

Generated from persistent GitHub checkpoints; no private/leaked/home contact data is used.
