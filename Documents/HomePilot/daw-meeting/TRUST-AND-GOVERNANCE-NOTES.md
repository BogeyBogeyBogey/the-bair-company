# Trust and Governance Notes

## Wat je veilig mag zeggen

- "De demo gebruikt synthetische adressen en fictieve funnelcijfers."
- "In productie gebruiken we publieke gebouw- en omgevingsbronnen, geen gekochte persoonsgegevens."
- "Scores zijn opportunity signals, geen voorspelling van koopintentie."
- "Contactgegevens ontstaan pas wanneer een bewoner zelf reageert."
- "Bron, licentie, ophaaldatum en freshness worden per bron geregistreerd."
- "Productie-scoping per tenant en partner wordt in Postgres/Supabase RLS afgedwongen en getest voor live outreach."

## Wat je niet mag zeggen

- "Deze bewoners willen renoveren."
- "Dit zijn warme leads."
- "De 33% respons is een benchmark."
- "We hebben contactgegevens van eigenaars."
- "Dit is vandaag enterprise production-ready."
- "DAW leert automatisch van andere klanten."

## Productie-hardening als pilot-deliverables

1. Productiedatabase met tenant-, module- en partner-scoping.
2. RLS-testbewijs voor DAW en partners.
3. Sources registry met licentie, ophaaldatum, dekking en eigenaar.
4. Exportlog met actor, scope, record count en timestamp.
5. Audit log voor statuswijzigingen en assignments.
6. Partner-weekrapport en 3-knops statusupdate.
7. Outcome-import voor afspraak, offerte, won/lost, project m2 en materiaalomzet.
8. Security-onepager, DPA-template en verwerkingsregister.
9. Monitoring en incident-runbook.

## Antwoord op moeilijke vragen

**"Mag dit onder GDPR?"**
"Daarom is de demo synthetisch. In productie werken we op gebouwniveau met publieke bronnen. Persoonsgegevens ontstaan pas bij vrijwillige respons, met basis en timestamp. Het bronnenregister tekenen we vooraf met legal af."

**"Waarom zouden partners dit invullen?"**
"Omdat hun view geen CRM wordt maar een korte werklijst: nieuw, opvolgen, afspraak, niet relevant. Adoptie is een pilot-KPI, en ik draai de wekelijkse sync mee."

**"Wat als jij wegvalt?"**
"De pilot draait op standaardinfrastructuur en alle data/learnings blijven contractueel van DAW. Export is altijd mogelijk. Voor een jaarcontract kunnen escrow en SLA mee in scope."

**"Waarom betalen wij en niet de verwerkers?"**
"Wie betaalt, stuurt. Als partners apart betalen, versnippert DAW de data. DAW moet de learning database bezitten; partners kunnen later via co-op bijdragen."

## Bronlinks voor bijlage

- Vlaanderen renovatieplicht residentiele gebouwen: https://www.vlaanderen.be/en/moving-housing-and-energy/renovation-obligation-for-residential-buildings
- Buitenmuurpremies 2026: https://www.mijnbenovatie.be/nl/stappen/buitenmuren/premies/
- Caparol thermische gevelisolatie systemen: https://www.caparol.be/producten/thermische-gevelisolatie-systemen
- WPP Open Intelligence: https://www.wppmedia.com/news/introducing-open-intelligence
