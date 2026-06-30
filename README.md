# PyPSA-Dashboard

plotly-based dashboard for interactive visualization of PyPSA-results

- **Ablage und Start:**  
  `Dashboard.py`, der Ordner `assets/map-icons` und die auszuwertenden `.nc`-Dateien müssen im selben Projektordner liegen. Benötigt werden insbesondere PyPSA, NumPy, pandas, Dash und Plotly; für den PDF-Export zusätzlich ReportLab und Pillow. Start über `python Dashboard.py`, anschließend Aufruf im Browser.

- **Datenformat:**  
  Das optimierte Netzwerk ist vollständig als NetCDF-Datei zu exportieren.

- **Sektoren und Carrier:**  
  Busse und Komponenten sind mit Carrier-Bezeichnungen nach dem Muster `Sektor_Unterkategorie` zu versehen. Das Dashboard trennt am ersten Unterstrich. Beispiele sind `Strom_Strom_PV` und `Wärme_Wärme_Gas`. Als Sektoren werden Strom und Wärme erkannt, andere Bezeichnungen werden `Sonstige` zugeordnet.

- **Investitionsperioden:**  
  Einjahres- und Multi-Investment-Period-Modelle werden unterstützt. Bei MIP müssen `investment_periods`, ein Snapshot-MultiIndex aus Investitionsperiode und Zeitschritt sowie `build_year` und `lifetime` der ausbaurelevanten Komponenten vorliegen. Ein Namenssuffix `_YYYY` unterstützt die Zuordnung, ersetzt eindeutige Metadaten jedoch nicht.

- **Leistungen:**  
  Optimierte Nennwerte müssen als `p_nom_opt`, `s_nom_opt` oder `e_nom_opt` exportiert werden.

- **Wirtschaftsmetadaten:**  
  Kostenrelevante Komponenten benötigen `lifetime`, annualisierte `capital_cost` und `marginal_cost`. `fixed_cost` ist bei fixen Betriebskosten zu ergänzen. Für eine eindeutige Darstellung der nicht annualisierten Investitionen werden `capital_cost_overnight` und `discount_rate` empfohlen.

- **CO2-Metadaten:**  
  Für emissionsrelevante Komponenten sind `co2_factor_kg_per_kwh`, `co2_price_eur_per_t`, `co2_port`, `co2_source` und möglichst `co2_scope` mit `scope_1`, `scope_2` oder `scope_3` zu hinterlegen. Mit `network.meta["co2_costs_in_marginal_cost"]` wird angegeben, ob CO2-Kosten bereits in `marginal_cost` enthalten sind oder nicht.

- **Benennung und Systemkarte:**  
  Eindeutige Namen mit Begriffen wie PV, BHKW, Wärmepumpe, Stromnetz_Bezug, Gasnetz_Bezug, Fernwärme_Bezug, Stromlast, Wärmelast, Stromnutzung oder Exportleitung verbessern die automatische Zuordnung. Die gemeinsame Überschusseinspeisung ist als Generator mit `sign = -1` abzubilden. Kartenkomponenten benötigen gültige x/y-Koordinaten in EPSG:4326 (`x = Längengrad`, `y = Breitengrad`). `map_label`, Quelle und Lagegenauigkeit ergänzen das Hovermenü. Ungültige Koordinaten sowie Komponenten ohne relevante Leistung oder Aktivität werden ausgeblendet.

- **Variantenvergleich und Export:**  
  Dateinamen sollten das Szenario eindeutig erkennen lassen. Vergleichsdateien sollten dieselben Einheiten, Snapshot-Gewichtungen und möglichst denselben Betrachtungszeitraum verwenden. PDF-Berichte werden bevorzugt im Downloads-Ordner gespeichert, ersatzweise im Projektordner `reports`. Fehlende optionale Daten führen zu Hinweisen oder deaktivierten Modulen.

Used Software:

Python: Version 3.12.13  
PyPSA: Version 1.1.2  
NumPy: Version 2.4.3  
pandas: Version 3.0.1  
Dash: Version 4.1.0  
Plotly: Version 6.6.0  
ReportLab: Version 4.5.0  
Pillow: Version 12.1.1  
Spyder: Version 6.1.3
