Inhoud
1. Sportfinder.py

Dit script genereert een interactieve kaart van Nederland met sportlocaties.

Functionaliteiten:

weergave van sportlocaties met marker clustering,

selecteren van een punt op de kaart,

analyse van sportlocaties binnen een instelbare straal,

overzicht per sport / activiteit,

resultaten gesorteerd op afstand.

De output is een interactieve HTML-kaart die lokaal in de browser kan worden geopend.

2. Kaart locaties.py

Dit script bouwt voort op de opgeschoonde dataset en verrijkt sportlocaties met extra informatie.

Onder andere:

openingstijden (uit CSV of via Google Places),

websites en social links,

Google Maps-links,

herkenning van sportketens en prijsindicaties,

speciale logica voor verhuurbare sportlocaties in Utrecht.

De resultaten worden weergegeven in een interactieve Folium-kaart met uitgebreide pop-ups.

Bestanden

Sportfinder.py – interactieve kaart met klik- en radiusanalyse

Kaart locaties.py – verrijkte visualisatie met extra locatie-informatie

nl_sports_facilities_clean.csv – opgeschoonde dataset met sportlocaties

*.html – gegenereerde interactieve kaarten# Sportfinder
-
