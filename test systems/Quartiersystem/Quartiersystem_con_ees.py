# -*- coding: utf-8 -*-
"""
Quartiersystem

Erzeugt ein Multi-Investment-Period-PyPSA-Netzwerk für das Quartiersystem.
Neben der Optimierungsstruktur werden Kosten-, CO2- und Kartenmetadaten
gespeichert, die das Dashboard später direkt aus der .nc-Datei ausliest.

@author: joshua
"""

from pathlib import Path

import pandas as pd
import pypsa

BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd().resolve()
PROFILE_FILENAME = "Quartier_2025_profiles.csv"


DISCOUNT_RATE = 0.05
STORAGE_UNIT_TIME_SERIES_DEFAULTS = {
    "standing_loss": 0.0,
    "efficiency_store": 1.0,
    "efficiency_dispatch": 1.0,
    "inflow": 0.0,
    "p_min_pu": 0.0,
    "p_max_pu": 1.0,
}

# Karten Metadaten
GEO_CRS_EPSG = "EPSG:4326"
GEO_CRS_NAME = "WGS 84"
GEO_AXIS_ORDER = "x=longitude, y=latitude"
GEO_COORDINATE_EPOCH = "not specified (conceptual model layout)"
GEO_LOCATION_SOURCE = "Konzeptionelles Dashboard-Layout; durch reale Standortkoordinaten ersetzen"
GEO_LOCATION_METHOD = "Manuell zugeordnetes Modelllayout"
GEO_LOCATION_ACCURACY_M = 1.5

# Geokoordinatentabelle der Komponenten
MAP_COORDS = {
    "Stromnetz-Bezug": (6.88380, 50.94564),
    "Gasnetz-Bezug": (6.88347, 50.94573),
    "Überschuss-Einspeisung": (6.88380, 50.94564),
    "PV G1": (6.883655, 50.945930),
    "PV G2": (6.883985, 50.945880),
    "PV G3": (6.884145, 50.946090),
    "PV G4": (6.884305, 50.946320),
    "PV G5": (6.883895, 50.946280),
    "Stromlast G1": (6.883655, 50.945850),
    "Stromlast G2": (6.883985, 50.945800),
    "Stromlast G3": (6.884145, 50.946010),
    "Stromlast G4": (6.884305, 50.946240),
    "Stromlast G5": (6.883895, 50.946200),
    "Wärmelast G1": (6.883765, 50.945850),
    "Wärmelast G2": (6.884095, 50.945800),
    "Wärmelast G3": (6.884255, 50.946010),
    "Wärmelast G4": (6.884415, 50.946240),
    "Wärmelast G5": (6.884005, 50.946200),
    "Wärmepumpe G1": (6.883765, 50.945930),
    "Wärmepumpe G2": (6.884095, 50.945880),
    "Wärmepumpe G3": (6.884255, 50.946090),
    "Wärmepumpe G4": (6.884415, 50.946320),
    "Wärmepumpe G5": (6.884005, 50.946280),
    "BHKW G5": (6.884035, 50.946240),
    "Stromspeicher G1": (6.88319, 50.94621),
    "Stromspeicher G2": (6.88354, 50.94670),
    "Wärmespeicher G1": (6.88374, 50.94580),
    "Wärmespeicher G2": (6.88398, 50.94613),
}

# Verknüpft PyPSA-Komponenten mit Kartenlabels und Koordinatenschlüsseln.
MAP_COMPONENT_GEO = [
    ("generators", "prefix", "Stromnetz_Bezug_", "Stromnetz-Bezug", "Stromnetz-Bezug"),
    ("generators", "prefix", "Gasnetz_Bezug_", "Gasnetz-Bezug", "Gasnetz-Bezug"),
    ("generators", "prefix", "Überschuss_Einspeisung_", "Überschuss-Einspeisung", "Überschuss-Einspeisung"),
    ("links", "period", "BHKW_G5_{period}", "BHKW G5 {period}", "BHKW G5"),
]

for house in range(1, 6):
    MAP_COMPONENT_GEO.extend([
        ("generators", "prefix", f"PV_G{house}_", f"PV G{house}", f"PV G{house}"),
        ("loads", "exact", f"Stromlast_G{house}", f"Stromlast G{house}", f"Stromlast G{house}"),
        ("loads", "exact", f"Wärmelast_G{house}", f"Wärmelast G{house}", f"Wärmelast G{house}"),
        ("links", "prefix", f"Wärmepumpe_G{house}_", f"Wärmepumpe G{house}", f"Wärmepumpe G{house}"),
    ])

for storage_name, label, coord_key in [
    ("Stromspeicher_G1", "Stromspeicher G1", "Stromspeicher G1"),
    ("Stromspeicher_G2", "Stromspeicher G2", "Stromspeicher G2"),
    ("Wärmespeicher_G1", "Wärmespeicher G1", "Wärmespeicher G1"),
    ("Wärmespeicher_G2", "Wärmespeicher G2", "Wärmespeicher G2"),
]:
    MAP_COMPONENT_GEO.extend([
        ("links", "period", f"{storage_name}_Laden_{{period}}", f"{label} Laden {{period}}", coord_key),
        ("links", "period", f"{storage_name}_Entladen_{{period}}", f"{label} Entladen {{period}}", coord_key),
        ("storage_units", "period", f"{storage_name}_{{period}}", f"{label} {{period}}", coord_key),
    ])


def pv_bus_name(house, period):
    """
    Erzeugt den periodenspezifischen PV-Busnamen eines Gebäudes.

    Inputs: Gebäudenummer und Investitionsperiode.
    Outputs: Busname als String.
    """
    return f"PV_Strom_Bus_G{int(house)}_{int(period)}"


def bhkw_strom_bus_name(period):
    """
    Erzeugt den periodenspezifischen Strombusnamen für das Quartiers-BHKW.

    Inputs: Investitionsperiode.
    Outputs: Busname als String.
    """
    return f"BHKW_Strom_Bus_G5_{int(period)}"


def annuity(rate, lifetime):
    """
    Berechnet den Annuitätsfaktor für Zinssatz und technische Lebensdauer.

    Inputs: Zinssatz und Lebensdauer.
    Outputs: Annuitätsfaktor.
    """
    if rate == 0:
        return 1 / lifetime
    return rate / (1 - (1 + rate) ** (-lifetime))


def annualized_cost(capex, lifetime, rate=DISCOUNT_RATE):
    """
    Rechnet einmalige Investitionskosten in jährliche Kapitalkosten um.

    Inputs: CAPEX, Lebensdauer und Zinssatz.
    Outputs: annualisierte Kosten.
    """
    return capex * annuity(rate, lifetime)


def set_component_financial_metadata(
    network,
    component,
    name,
    *,
    capital_cost_overnight=0.0,
    discount_rate=DISCOUNT_RATE,
    fixed_cost=0.0,
):
    """
    Speichert Investitions-, Zins- und Fixkostendaten direkt an der Komponente.

    Inputs: Netzwerk, Komponententyp, Name und Kostenparameter.
    Outputs: Inplace-Ergänzung der Komponententabelle.
    """
    table = getattr(network, component)
    defaults = {
        "capital_cost_overnight": 0.0,
        "discount_rate": DISCOUNT_RATE,
        "fixed_cost": 0.0,
    }
    for col, default in defaults.items():
        if col not in table.columns:
            table[col] = default
    if name not in table.index:
        return
    table.at[name, "capital_cost_overnight"] = float(capital_cost_overnight)
    table.at[name, "discount_rate"] = float(discount_rate)
    table.at[name, "fixed_cost"] = float(fixed_cost)


# Dateien einlesen
def read_quarter_profiles(filename):
    """
    Liest das gemeinsame Quartiersprofil und normalisiert Zeitindex und Zahlenwerte.

    Inputs: Dateiname des Quartiersprofils.
    Outputs: DataFrame mit Strom-, Wärme- und PV-Zeitreihen je Gebäude.
    """
    profile_path = BASE_DIR / filename

    df = pd.read_csv(
        profile_path,
        sep=";",
        decimal=","
    )

    required_columns = (
        ["date"]
        + [f"P_el_H{i}" for i in range(1, 6)]
        + [f"Q_htg_H{i}" for i in range(1, 6)]
        + [f"P_pv_H{i}" for i in range(1, 6)]
    )

    raw_dates = df["date"].astype(str).str.strip()
    iso_dates = pd.to_datetime(
        raw_dates.where(raw_dates.str.match(r"^\d{4}-\d{1,2}-\d{1,2}")),
        errors="coerce"
    )
    german_dates = pd.to_datetime(
        raw_dates.where(raw_dates.str.contains(r"\.", regex=True)),
        errors="coerce",
        dayfirst=True
    )
    slash_dates = pd.to_datetime(
        raw_dates.where(raw_dates.str.contains("/", regex=False)),
        errors="coerce",
        dayfirst=False
    )
    fallback_dates = pd.to_datetime(raw_dates, errors="coerce")
    df["date"] = iso_dates.fillna(german_dates).fillna(slash_dates).fillna(fallback_dates)
    df = df.dropna(subset=["date"])
    df = df.drop_duplicates(subset=["date"], keep="first")
    df = df.set_index("date").sort_index()
    for column in required_columns[1:]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return df[required_columns[1:]]

# Übertragen des Datumsprofils in ein anderes Jahr
def shift_index_to_year(index, year):
    """
    Überträgt ein Zeitprofil auf ein anderes Kalenderjahr.

    Inputs: ursprünglicher DatetimeIndex und Zieljahr.
    Outputs: neuer DatetimeIndex mit gleicher zeitlicher Struktur im Zieljahr.
    """
    return pd.DatetimeIndex([ts.replace(year=year) for ts in index])

# Zeitachse für alle Investitionsjahre
def build_multi_invest_snapshots(base_index, investment_periods):
    """
    Baut die Snapshot-Struktur aus Investitionsperiode und Zeitstempel.

    Inputs: Basiszeitindex und Liste der Investitionsperioden.
    Outputs: MultiIndex mit period und timestep.
    """
    arrays = []
    for period in investment_periods:
        shifted_index = shift_index_to_year(base_index, period)
        arrays.extend((period, ts) for ts in shifted_index)
    return pd.MultiIndex.from_tuples(arrays, names=["period", "timestep"])

# kopiert Zeitreihe für alle Investitionsjahre
def expand_series_to_period_snapshots(series, investment_periods):
    """
    Kopiert eine Zeitreihe in die Snapshot-Struktur aller Investitionsperioden.

    Inputs: Basiszeitreihe und Investitionsperioden.
    Outputs: Series mit MultiIndex aus period und timestep.
    """
    blocks = []
    for period in investment_periods:
        shifted = series.copy()
        shifted.index = pd.MultiIndex.from_arrays(
            [
                pd.Index([period] * len(series), name="period"),
                shift_index_to_year(series.index, period),
            ],
            names=["period", "timestep"]
        )
        blocks.append(shifted)
    return pd.concat(blocks)

def _snapshot_index_for_xarray(index):
    """
    Erzeugt einen für xarray eindeutig benannten Snapshot-MultiIndex.

    Inputs: vorhandener Snapshotindex.
    Outputs: MultiIndex mit Namen period und timestep sowie Gesamtname snapshot.
    """
    snapshots = pd.MultiIndex.from_tuples(
        list(index),
        names=["period", "timestep"]
    )
    snapshots.name = "snapshot"
    return snapshots


def _set_time_dependent_frame(container, attr, frame):
    """
    Schreibt eine dynamische PyPSA-Zeitreihentabelle.

    Inputs: Zeitreihencontainer, Attributname und DataFrame.
    Outputs: Inplace-Zuweisung.
    """
    try:
        container[attr] = frame
    except TypeError:
        setattr(container, attr, frame)


def ensure_storage_unit_time_series_defaults(network, snapshots):
    """
    Stellt vollständige StorageUnit-Zeitreihen sicher.

    Inputs: PyPSA-Netzwerk und Snapshotindex.
    Outputs: Inplace-Ergänzung fehlender StorageUnit-Zeitreihen.
    """
    if len(network.storage_units.index) == 0:
        return

    storage_names = network.storage_units.index

    for attr, fallback in STORAGE_UNIT_TIME_SERIES_DEFAULTS.items():
        static_values = (
            network.storage_units[attr]
            if attr in network.storage_units.columns
            else pd.Series(fallback, index=storage_names)
        )
        static_values = static_values.reindex(storage_names).fillna(fallback)

        frame = pd.DataFrame(index=snapshots, columns=storage_names, dtype=float)
        for storage_name in storage_names:
            frame[storage_name] = float(static_values.at[storage_name])

        frame.index = snapshots
        _set_time_dependent_frame(network.storage_units_t, attr, frame)


def normalize_multi_investment_snapshot_index(network):
    """
    Sorgt dafür, dass alle Zeitreihen der Multi-Investment-Snapshots und der StorageUnits
    denselben Snapshot-Index benutzen.

    Inputs: PyPSA-Netzwerk.
    Outputs: Inplace-Normalisierung von Snapshots und dynamischen Tabellen.
    """
    if isinstance(network.snapshots, pd.MultiIndex):
        snapshots = _snapshot_index_for_xarray(network.snapshots)
        network.snapshots = snapshots
        network.snapshot_weightings = network.snapshot_weightings.reindex(snapshots)
        network.snapshot_weightings.index = snapshots

        for container_name in [
            "generators_t",
            "loads_t",
            "links_t",
            "storage_units_t",
            "stores_t",
            "lines_t",
            "transformers_t",
        ]:
            container = getattr(network, container_name, None)
            if container is None:
                continue

            for attr, values in list(container.items()):
                if isinstance(values, pd.DataFrame):
                    values = values.copy()
                    if len(values.index) == len(snapshots):
                        values.index = snapshots
                    else:
                        values = values.reindex(snapshots)
                    container[attr] = values
                elif isinstance(values, pd.Series):
                    values = values.copy()
                    if len(values.index) == len(snapshots):
                        values.index = snapshots
                    else:
                        values = values.reindex(snapshots)
                    container[attr] = values

        ensure_storage_unit_time_series_defaults(network, snapshots)

# prüft in welchen Jahren eine Komponente aktiv ist
def patch_pypsa_expand_series_for_multiindex_snapshots():
    """
    Sichert die interne PyPSA/xarray-Konvertierung für MultiIndex-Snapshots ab.

    Inputs: keine expliziten Parameter.
    Outputs: Inplace-Patch der PyPSA-Hilfsfunktion.
    """
    try:
        import pypsa.common as pypsa_common
        import pypsa.optimization.constraints as pypsa_constraints
    except ImportError:
        return

    current_expand_series = pypsa_constraints.expand_series
    if getattr(current_expand_series, "_quartier_multiindex_patch", False):
        return

    original_expand_series = getattr(
        current_expand_series,
        "_quartier_original_expand_series",
        current_expand_series
    )

    def expand_series_with_named_snapshot_index(series, columns):
        """
        Erweitert PyPSA-Zeitreihen mit benannter Snapshot-Dimension.

        Inputs: Series und Zielspalten.
        Outputs: DataFrame mit korrekt benanntem Snapshot- und Komponentenindex.
        """
        result = original_expand_series(series, columns)

        if isinstance(result.index, pd.MultiIndex) and result.index.name != "snapshot":
            result.index = result.index.copy()
            result.index.name = "snapshot"
        elif not isinstance(result.index, pd.MultiIndex) and result.index.name in (None, "dim_0"):
            result.index.name = "snapshot"

        if result.columns.name in (None, "dim_1"):
            result.columns.name = "name"

        return result

    expand_series_with_named_snapshot_index._quartier_multiindex_patch = True
    expand_series_with_named_snapshot_index._quartier_original_expand_series = original_expand_series
    pypsa_common.expand_series = expand_series_with_named_snapshot_index
    pypsa_constraints.expand_series = expand_series_with_named_snapshot_index


def optimize_with_multiindex_storage_fix(network, **kwargs):
    """
    Startet die PyPSA-Optimierung mit vorheriger MultiIndex-Korrektur.

    Inputs: PyPSA-Netzwerk und Optimierungsargumente.
    Outputs: Ergebnis von network.optimize.
    """
    normalize_multi_investment_snapshot_index(network)
    patch_pypsa_expand_series_for_multiindex_snapshots()
    return network.optimize(**kwargs)


def _linopy_variable_item(variable, name):
    """
    Holt aus einer Optimierungs-Tabelle genau den Eintrag mit einem bestimmten Namen.

    Inputs: Linopy-Variable und Komponentenname.
    Outputs: ausgewähltes Variablenelement.
    """
    try:
        return variable.loc[name]
    except Exception:
        return variable.loc[{"name": name}]


def couple_gas_grid_to_chp_capacity(network, snapshots):
    """
    Koppelt die optimierte Gasnetz-Bezugsleistung an die BHKW-Leistung.

    Inputs: PyPSA-Netzwerk und Snapshots.
    Outputs: zusätzliche Linopy-Nebenbedingungen im Optimierungsmodell.
    """
    model = network.model
    try:
        gas_capacity = model.variables["Generator-p_nom"]
        chp_capacity = model.variables["Link-p_nom"]
    except KeyError:
        return

    for period in investment_periods:
        gas_name = f"Gasnetz_Bezug_{period}"
        chp_name = f"BHKW_G5_{period}"
        if gas_name not in network.generators.index or chp_name not in network.links.index:
            continue
        model.add_constraints(
            _linopy_variable_item(gas_capacity, gas_name) == _linopy_variable_item(chp_capacity, chp_name),
            name=f"Gasnetz_BHKW_Kopplung_{period}",
        )


def co2_cost_per_kwh(co2_factor_kg_per_kwh, co2_price_eur_per_t):
    """
    Wandelt CO2-Faktor und CO2-Preis in variable CO2-Kosten je kWh um.

    Inputs: CO2-Faktor in kg/kWh und CO2-Preis in EUR/t.
    Outputs: CO2-Kosten in EUR/kWh.
    """
    try:
        factor = float(co2_factor_kg_per_kwh)
        price = float(co2_price_eur_per_t)
    except Exception:
        return 0.0
    return factor / 1000.0 * price


def set_component_co2_metadata(
    network,
    component,
    name,
    *,
    co2_factor_kg_per_kwh=0.0,
    co2_price_eur_per_t=0.0,
    co2_port="p",
    co2_scope="",
    co2_source=""
):
    """
    Hinterlegt CO2-Faktor, Preis, Scope und Quelle für die spätere Dashboard-Auswertung.

    Inputs: Netzwerk, Komponententyp, Name und CO2-Metadaten.
    Outputs: Inplace-Ergänzung der Komponententabelle.
    """
    table = getattr(network, component)
    defaults = {
        "co2_factor_kg_per_kwh": 0.0,
        "co2_price_eur_per_t": 0.0,
        "co2_cost_eur_per_kwh": 0.0,
        "co2_port": "",
        "co2_scope": "",
        "co2_source": ""
    }
    for col, default in defaults.items():
        if col not in table.columns:
            table[col] = default
    if name not in table.index:
        return

    table.at[name, "co2_factor_kg_per_kwh"] = float(co2_factor_kg_per_kwh)
    table.at[name, "co2_price_eur_per_t"] = float(co2_price_eur_per_t)
    table.at[name, "co2_cost_eur_per_kwh"] = co2_cost_per_kwh(
        co2_factor_kg_per_kwh, co2_price_eur_per_t
    )
    table.at[name, "co2_port"] = str(co2_port)
    table.at[name, "co2_scope"] = str(co2_scope)
    table.at[name, "co2_source"] = str(co2_source)


def _ensure_geo_columns(table):
    """
    Legt alle für die Systemkarte benötigten Geodatenspalten an.

    Inputs: statische PyPSA-Komponententabelle.
    Outputs: Inplace-Ergänzung fehlender Spalten.
    """
    defaults = {
        "x": float("nan"),
        "y": float("nan"),
        "crs_epsg": "",
        "crs_name": "",
        "coordinate_axis_order": "",
        "coordinate_epoch": "",
        "location_accuracy_m": float("nan"),
        "location_source": "",
        "location_method": "",
        "map_label": "",
    }
    for col, default in defaults.items():
        if col not in table.columns:
            table[col] = default


def set_component_geo_metadata(
    network,
    component,
    name,
    *,
    x,
    y,
    map_label="",
    location_accuracy_m=GEO_LOCATION_ACCURACY_M,
    location_source=GEO_LOCATION_SOURCE,
    location_method=GEO_LOCATION_METHOD,
):
    """
    Schreibt Koordinate, CRS und Kartenlabel an eine einzelne PyPSA-Komponente.

    Inputs: Netzwerk, Komponententyp, Name, Koordinate und Kartenmetadaten.
    Outputs: Inplace-Ergänzung der Geometadaten.
    """
    table = getattr(network, component)
    _ensure_geo_columns(table)
    if name not in table.index:
        return

    table.at[name, "x"] = float(x)
    table.at[name, "y"] = float(y)
    table.at[name, "crs_epsg"] = GEO_CRS_EPSG
    table.at[name, "crs_name"] = GEO_CRS_NAME
    table.at[name, "coordinate_axis_order"] = GEO_AXIS_ORDER
    table.at[name, "coordinate_epoch"] = GEO_COORDINATE_EPOCH
    table.at[name, "location_accuracy_m"] = float(location_accuracy_m)
    table.at[name, "location_source"] = str(location_source)
    table.at[name, "location_method"] = str(location_method)
    table.at[name, "map_label"] = str(map_label or name)


def export_network_safely(network, target_path):
    """
    Exportiert zunächst in eine temporäre Datei und ersetzt die finale .nc-Datei erst nach erfolgreicher Prüfung.

    Inputs: PyPSA-Netzwerk und Zielpfad.
    Outputs: geschriebene NetCDF-Datei oder Fehler mit bereinigter temporärer Datei.
    """
    target_path = Path(target_path)
    temp_path = target_path.with_name(f"{target_path.stem}.tmp{target_path.suffix}")
    if temp_path.exists():
        temp_path.unlink()
    try:
        network.export_to_netcdf(temp_path)
        temp_path.replace(target_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def apply_system_geo_metadata(network, investment_periods):
    """
    Hinterlegt CRS-, Quellen- und Lagequalitätsangaben für die Systemkarte.
    
    Inputs: PyPSA-Netzwerk und Investitionsperioden.
    Outputs: Inplace-Ergänzung von Netzwerk- und Komponentenmetadaten.
    """
    if not hasattr(network, "meta") or network.meta is None:
        network.meta = {}
    network.meta["spatial_crs_epsg"] = GEO_CRS_EPSG
    network.meta["spatial_crs_name"] = GEO_CRS_NAME
    network.meta["spatial_coordinate_axis_order"] = GEO_AXIS_ORDER
    network.meta["spatial_coordinate_epoch"] = GEO_COORDINATE_EPOCH
    network.meta["spatial_location_source"] = GEO_LOCATION_SOURCE
    network.meta["spatial_location_method"] = GEO_LOCATION_METHOD
    network.meta["spatial_location_accuracy_m"] = GEO_LOCATION_ACCURACY_M
    network.meta["spatial_data_quality_scope"] = "PyPSA-Komponenten der Systemkarte"
    network.meta["spatial_lineage"] = "Konzeptionelle Standortzuordnung im Quartiersystem_pro_ees.py"

    def apply_map_entry(component, match_mode, pattern, label_template, coord_key):
        """
        Überträgt Koordinaten und Kartenbeschriftungen auf passende Komponenten.

        Inputs: Komponententyp, Suchmodus, Namensmuster, Labelvorlage und Koordinatenschlüssel.
        Outputs: Inplace-Ergänzung der Geometadaten an passenden Komponenten.
        """
        table = getattr(network, component, None)
        if table is None or table.empty or coord_key not in MAP_COORDS:
            return
        x, y = MAP_COORDS[coord_key]
        if match_mode == "prefix":
            for name in table.index:
                if str(name).startswith(pattern):
                    suffix = str(name)[len(pattern):]
                    display = f"{label_template} {suffix}".strip()
                    set_component_geo_metadata(network, component, name, x=x, y=y, map_label=display)
        elif match_mode == "exact":
            if pattern in table.index:
                set_component_geo_metadata(network, component, pattern, x=x, y=y, map_label=label_template)
        elif match_mode == "period":
            for period in investment_periods:
                name = pattern.format(period=period)
                if name in table.index:
                    label = label_template.format(period=period)
                    set_component_geo_metadata(network, component, name, x=x, y=y, map_label=label)

    for entry in MAP_COMPONENT_GEO:
        apply_map_entry(*entry)


#%% Optimierungsstruktur für Speicher
def add_optimizable_storage_assets(network, storage_configs, investment_periods):
    """
    Legt Speicher mit Lade-, Entlade- und Energiekomponente als optimierbare MIP-Anlagen an.

    Inputs: PyPSA-Netzwerk, Speicherkonfigurationen und Investitionsperioden.
    Outputs: Inplace-Ergänzung von Links und StorageUnits.
    """
    for cfg in storage_configs:
        for period, factor in cfg["period_factors"].items():
            power_cap = float(cfg["base_power"] * factor)
            if power_cap <= 0:
                continue

            charge_name = f"{cfg['name']}_Laden_{period}"
            discharge_name = f"{cfg['name']}_Entladen_{period}"
            storage_name = f"{cfg['name']}_{period}"

            network.add(
                "Link",
                charge_name,
                bus0=cfg["main_bus"],
                bus1=cfg["storage_bus"],
                carrier=cfg["carrier"],
                p_nom_extendable=True,
                p_nom_min=0.0,
                p_nom_max=power_cap,
                build_year=period,
                lifetime=cfg["lifetime"],
                efficiency=cfg["charge_efficiency"],
                capital_cost=annualized_cost(cfg["power_costs"][period], cfg["lifetime"]),
                marginal_cost=0.0
            )

            network.add(
                "Link",
                discharge_name,
                bus0=cfg["storage_bus"],
                bus1=cfg["main_bus"],
                carrier=cfg["carrier"],
                p_nom_extendable=True,
                p_nom_min=0.0,
                p_nom_max=power_cap,
                build_year=period,
                lifetime=cfg["lifetime"],
                efficiency=cfg["discharge_efficiency"],
                capital_cost=annualized_cost(cfg["power_costs"][period], cfg["lifetime"]),
                marginal_cost=0.0
            )

            network.add(
                "StorageUnit",
                storage_name,
                bus=cfg["storage_bus"],
                carrier=cfg["carrier"],
                p_nom_extendable=True,
                p_nom_min=0.0,
                p_nom_max=power_cap,
                build_year=period,
                lifetime=cfg["lifetime"],
                cyclic_state_of_charge=True,
                standing_loss=cfg["standing_loss"],
                efficiency_store=1.0,
                efficiency_dispatch=1.0,
                max_hours=cfg["max_hours"],
                capital_cost=annualized_cost(
                    cfg["energy_costs"][period] * cfg["max_hours"],
                    cfg["lifetime"]
                ),
                marginal_cost=cfg.get("marginal_cost", 0.0)
            )


#%% Profile einlesen
profiles = read_quarter_profiles(PROFILE_FILENAME)

load_el_cols = [f"P_el_H{i}" for i in range(1, 6)]
load_th_cols = [f"Q_htg_H{i}" for i in range(1, 6)]
pv_cols = [f"P_pv_H{i}" for i in range(1, 6)]

# Von Wh/Tag zu kW
profiles[load_el_cols] = profiles[load_el_cols] / 24 / 1000
profiles[load_th_cols] = profiles[load_th_cols] / 24 / 1000
profiles[pv_cols] = profiles[pv_cols] / 24 / 1000

# Skalierung der Profile auf ein passendes Niveau
electricity_load_scale = 1.15
heat_load_scale = 1.30
profiles[load_el_cols] *= electricity_load_scale
profiles[load_th_cols] *= heat_load_scale


#%% Dashboard-taugliche Zeitauflösung
USE_WEEKLY_RESOLUTION = False

if USE_WEEKLY_RESOLUTION:
    profiles = profiles.resample("W-MON").mean()


#%% Variablen
investment_periods = [2025, 2030, 2040, 2050]
multi_invest_snapshots = build_multi_invest_snapshots(profiles.index, investment_periods)

houses = [1, 2, 3, 4, 5]
heat_pump_houses = [1, 2, 3, 4]
storage_houses = [1, 2]

# Effizienzen
efficiency_th_bhkw = 0.50
efficiency_el_bhkw = 0.35
efficiency_cop_wp = 4.5
efficiency_el_storage = 0.95
efficiency_th_storage = 0.90

# Preisentwicklungen
wp_cost = {2025: 1900, 2030: 1750, 2040: 1550, 2050: 1400}      # €/kW_el
pv_cost = {2025: 1250, 2030: 1150, 2040: 1050, 2050: 950}        # €/kW_el
bhkw_cost = {2025: 1700, 2030: 1750, 2040: 1850, 2050: 2000}     # €/kW
storage_el_cost = {2025: 600, 2030: 520, 2040: 460, 2050: 400}   # €/kWh_el
storage_th_cost = {2025: 12, 2030: 11, 2040: 10, 2050: 9}        # €/kWh_th
co2_price = {2025: 55, 2030: 100, 2040: 160, 2050: 220}          # €/t
co2_factor_grid = {2025: 0.36, 2030: 0.2, 2040: 0.08, 2050: 0}  # kg/kWh
co2_factor_gas = {2025: 0.2, 2030: 0.2, 2040: 0.2, 2050: 0.2}   # kg/kWh

# Lebensdauern
wp_lifetime = 15                               # Jahre
pv_lifetime = 25                               # Jahre
bhkw_lifetime = 10                             # Jahre
storage_el_lifetime = 15                       # Jahre
storage_th_lifetime = 20                       # Jahre

# Energiekosten
marginal_cost_grid = {2025: 0.30, 2030: 0.34, 2040: 0.39, 2050: 0.44}       # €/kWh
marginal_cost_gas = {2025: 0.11, 2030: 0.12, 2040: 0.15, 2050: 0.18}        # €/kWh

# Einspeisung (Strom)
feed_in_tariff_pv = {2025: 0.06, 2030: 0.04, 2040: 0.03, 2050: 0.02}        # €/kWh
feed_in_tariff_bhkw = {2025: 0.08, 2030: 0.075, 2040: 0.07, 2050: 0.065}    # €/kWh
FEED_IN_TARIFF_FIXED_YEARS = 20

# Status Komponenten
def feed_in_tariff_for_build(build_period, active_period, tariff_by_period):
    """
    Bestimmt die Einspeisevergütung: 20 Jahre fester Tarif ab Zubau, danach Periodentarif.

    Inputs: Bauperiode, aktive Periode und Tarifreihe.
    Outputs: Tarifwert und Kennzeichnung des Tarifmodus.
    """
    build_period = int(build_period)
    active_period = int(active_period)
    if active_period < build_period + FEED_IN_TARIFF_FIXED_YEARS:
        return float(tariff_by_period[build_period]), "fixed_20y"
    return float(tariff_by_period[active_period]), "active_period"


def component_active_in_period(build_period, active_period, lifetime):
    """
    Prüft, ob eine Komponente in der betrachteten Investitionsperiode aktiv ist.

    Inputs: Bauperiode, aktive Periode und Lebensdauer.
    Outputs: True, wenn die Komponente aktiv ist, sonst False.
    """
    build_period = int(build_period)
    active_period = int(active_period)
    return build_period <= active_period < build_period + int(lifetime)

# Speicherdimensionierung
max_hours_el_storage = 6.0
max_hours_th_storage = 20.0

# Ermitteln der Spitzenlast (Häuser)
peak_el_loads = {i: float(profiles[f"P_el_H{i}"].max()) for i in houses}
peak_th_loads = {i: float(profiles[f"Q_htg_H{i}"].max()) for i in houses}
peak_pv_generation = {i: float(profiles[f"P_pv_H{i}"].max()) for i in houses}

# Ermitteln der Spitzenlast (gesamt)
district_el_profile = profiles[[f"P_el_H{i}" for i in houses]].sum(axis=1)
district_heat_profile = profiles[[f"Q_htg_H{i}" for i in houses]].sum(axis=1)
peak_el_load_total = float(district_el_profile.max())
peak_heat_load_total = float(district_heat_profile.max())

# Leistungsdimensionierung
p_nom_max_pv = {i: max(peak_pv_generation[i] * 2.5, 5.0) for i in houses}
p_nom_max_wp = {
    i: max((peak_th_loads[i] / efficiency_cop_wp) * 1.6, 2.0) for i in heat_pump_houses
}
p_nom_min_bhkw = 0.0
p_nom_max_bhkw = max(p_nom_min_bhkw, peak_heat_load_total / efficiency_th_bhkw * 1.05)

# Begrenzung der Leistungsflüsse
free_transfer_capacity = max(
    2.0 * peak_el_load_total,
    sum(p_nom_max_pv.values()),
    p_nom_max_bhkw,
    180.0
)
house_link_capacity = {
    i: max(2.0 * peak_el_loads[i], p_nom_max_pv[i], 10.0) for i in houses
}
pv_export_capacity = {i: 0.45 * p_nom_max_pv[i] for i in houses}
bhkw_electric_capacity = p_nom_max_bhkw * efficiency_el_bhkw
bhkw_export_capacity = bhkw_electric_capacity
bezugsleistung_tie_breaker_cost = 1e-9


#%% Netzwerk
n = pypsa.Network()

# Investitionsperioden setzen
n.set_investment_periods(investment_periods)
n.set_snapshots(multi_invest_snapshots)
normalize_multi_investment_snapshot_index(n)

a = n.investment_period_weightings
a.loc[2025, "years"] = 5
a.loc[2030, "years"] = 10
a.loc[2040, "years"] = 10
a.loc[2050, "years"] = 10
a["objective"] = a["years"]

n.snapshot_weightings.loc[:, "objective"] = 24.0
n.snapshot_weightings.loc[:, "generators"] = 24.0
n.snapshot_weightings.loc[:, "stores"] = 24.0


#%% Zeitreihen auf PyPSA-Snapshots mappen
pv_pu = {}
load_el_mapped = {}
load_th_mapped = {}

# Verhindert einen überproportionalen PV-Zubau
for i in houses:
    pv_series = profiles[f"P_pv_H{i}"]
    pv_peak = max(float(pv_series.max()), 1e-9)
    pv_shape = pv_series / pv_peak

# kopiert die Zeitreihe für alle Investitionsjahre
    pv_pu[i] = expand_series_to_period_snapshots(pv_shape.clip(lower=0.0, upper=1.0), investment_periods)
    load_el_mapped[i] = expand_series_to_period_snapshots(profiles[f"P_el_H{i}"], investment_periods)
    load_th_mapped[i] = expand_series_to_period_snapshots(profiles[f"Q_htg_H{i}"], investment_periods)


#%% Carrier
carrier_names = [
    "Strom_Strom",
    "Strom_Strom_Netzbezug",
    "Strom_Strom_PV",
    "Strom_Strom_BHKW",
    "Strom_Strom_Speicher",
    "Strom_Strom_Einspeisung",
    "Strom_Strom_Last",
    "Wärme_Wärme",
    "Wärme_Wärme_Speicher",
    "Wärme_Wärme_Last",
    "Wärme_Wärme_Gas",
    "Wärme_Wärme_Gasnetz"
]
for carrier in carrier_names:
    n.add("Carrier", carrier)

# Hinterlegen der konstanten Emissionen auf den Carriern
n.carriers.loc[:, "co2_emissions"] = 0.0
n.carriers.at["Wärme_Wärme_Gas", "co2_emissions"] = co2_factor_gas[2025]
n.carriers.at["Wärme_Wärme_Gasnetz", "co2_emissions"] = co2_factor_gas[2025]


#%% Busse
n.add("Bus", "Strom_Bus", carrier="Strom_Strom")
n.add("Bus", "Wärme_Bus", carrier="Wärme_Wärme")
n.add("Bus", "Gas_Bus", carrier="Wärme_Wärme_Gas")
n.add("Bus", "Überschuss_Einspeisebus", carrier="Strom_Strom_Einspeisung")

for i in houses:
    n.add("Bus", f"Strom_Bus_G{i}", carrier="Strom_Strom")
    for period in investment_periods:
        n.add("Bus", pv_bus_name(i, period), carrier="Strom_Strom_PV")

for period in investment_periods:
    n.add("Bus", bhkw_strom_bus_name(period), carrier="Strom_Strom_BHKW")

for i in storage_houses:
    n.add("Bus", f"Stromspeicher_Bus_G{i}", carrier="Strom_Strom_Speicher")
    n.add("Bus", f"Wärmespeicher_Bus_G{i}", carrier="Wärme_Wärme_Speicher")


#%% Generatoren und Konverter
period_lifetimes = {2025: 5, 2030: 10, 2040: 10, 2050: 10}

for period in investment_periods:
    # Stromnetz
    n.add(
        "Generator",
        f"Stromnetz_Bezug_{period}",
        bus="Strom_Bus",
        carrier="Strom_Strom_Netzbezug",
        p_nom_extendable=True,
        p_nom_min=0.0,
        p_nom_max=free_transfer_capacity,
        build_year=period,
        lifetime=period_lifetimes[period],
        capital_cost=bezugsleistung_tie_breaker_cost,
        marginal_cost=(
            marginal_cost_grid[period]
            + co2_cost_per_kwh(co2_factor_grid[period], co2_price[period])
        )       # €/kWh inkl. CO2
    )

    # Gasnetz
    n.add(
        "Generator",
        f"Gasnetz_Bezug_{period}",
        bus="Gas_Bus",
        carrier="Wärme_Wärme_Gasnetz",
        p_nom_extendable=True,
        p_nom_min=0.0,
        build_year=period,
        lifetime=period_lifetimes[period],
        capital_cost=bezugsleistung_tie_breaker_cost,
        marginal_cost=(
            marginal_cost_gas[period]
            + co2_cost_per_kwh(co2_factor_gas[period], co2_price[period])
        )       # €/kWh inkl. CO2
    )

    # Gemeinsamer negativer Generator für PV- und BHKW-Überschussstrom
    n.add(
        "Generator",
        f"Überschuss_Einspeisung_{period}",
        bus="Überschuss_Einspeisebus",
        carrier="Strom_Strom_Einspeisung",
        sign=-1.0,
        p_nom=sum(pv_export_capacity.values()) + bhkw_export_capacity,
        build_year=period,
        lifetime=period_lifetimes[period],
        marginal_cost=0.0
    )

    for i in houses:
    # PV (für jedes Haus)
        n.add(
            "Generator",
            f"PV_G{i}_{period}",
            bus=pv_bus_name(i, period),
            carrier="Strom_Strom_PV",
            p_nom_extendable=True,
            p_nom_max=p_nom_max_pv[i],
            build_year=period,
            lifetime=pv_lifetime,
            capital_cost=annualized_cost(pv_cost[period], pv_lifetime),         # nach Investitionsperiode (€/kW_el)
            marginal_cost=0.0,
            p_max_pu=pv_pu[i]
        )


#%% Links
    for i in heat_pump_houses:
    # Wärmepumpe (für vier Häuser)
        n.add(
            "Link",
            f"Wärmepumpe_G{i}_{period}",
            bus0="Strom_Bus",
            bus1="Wärme_Bus",
            carrier="Strom_Strom",
            p_nom_extendable=True,
            p_nom_min=0.0,
            p_nom_max=p_nom_max_wp[i],
            build_year=period,
            lifetime=wp_lifetime,
            efficiency=efficiency_cop_wp,
            capital_cost=annualized_cost(wp_cost[period], wp_lifetime),               # nach Investitionsperiode (€/kW_th)
            marginal_cost=0.0
        )

    # BHKW
    n.add(
        "Link",
        f"BHKW_G5_{period}",
        bus0="Gas_Bus",
        bus1=bhkw_strom_bus_name(period),
        bus2="Wärme_Bus",
        carrier="Wärme_Wärme_Gas",
        p_nom_extendable=True,
        p_nom_min=p_nom_min_bhkw,
        p_nom_max=p_nom_max_bhkw,
        build_year=period,
        lifetime=bhkw_lifetime,
        efficiency=efficiency_el_bhkw,
        efficiency2=efficiency_th_bhkw,
        capital_cost=annualized_cost(bhkw_cost[period] * efficiency_el_bhkw, bhkw_lifetime), # €/kW_el auf Link-Eingangsleistung umgerechnet
        marginal_cost=0.0                                                           # Gasbezugskosten liegen am Gasnetz_Bezug
    )


#%% Netzverbindungen
for i in houses:
    # Hausanschlussleitungen
    n.add(
        "Link",
        f"Quartiersleitung_G{i}",
        bus0=f"Strom_Bus_G{i}",
        bus1="Strom_Bus",
        carrier="Strom_Strom",
        p_nom=house_link_capacity[i],
        p_min_pu=-1.0,
        efficiency=1.0,
        marginal_cost=0.0
    )

# Stromnutzung und Einspeisung je Anlagenjahrgang.
for build_period in investment_periods:
    for i in houses:
        n.add(
            "Link",
            f"PV_Stromnutzung_G{i}_{build_period}",
            bus0=pv_bus_name(i, build_period),
            bus1=f"Strom_Bus_G{i}",
            carrier="Strom_Strom_PV",
            p_nom=house_link_capacity[i],
            build_year=build_period,
            lifetime=pv_lifetime,
            efficiency=1.0,
            marginal_cost=0.0,
        )

    n.add(
        "Link",
        f"BHKW_Stromnutzung_G5_{build_period}",
        bus0=bhkw_strom_bus_name(build_period),
        bus1="Strom_Bus",
        carrier="Strom_Strom_BHKW",
        p_nom=bhkw_electric_capacity,
        build_year=build_period,
        lifetime=bhkw_lifetime,
        efficiency=1.0,
        marginal_cost=0.0,
    )

    for active_period in investment_periods:
        if component_active_in_period(build_period, active_period, pv_lifetime):
            tariff, tariff_mode = feed_in_tariff_for_build(
                build_period, active_period, feed_in_tariff_pv
            )
            for i in houses:
                link_name = f"PV_Exportleitung_G{i}_{build_period}_{active_period}"
                n.add(
                    "Link",
                    link_name,
                    bus0=pv_bus_name(i, build_period),
                    bus1="Überschuss_Einspeisebus",
                    carrier="Strom_Strom_Einspeisung",
                    p_nom=pv_export_capacity[i],
                    build_year=active_period,
                    lifetime=period_lifetimes[active_period],
                    efficiency=1.0,
                    marginal_cost=-tariff,       # Erlös = negative Kosten
                )
                n.links.at[link_name, "feed_in_tariff_eur_per_kwh"] = tariff
                n.links.at[link_name, "feed_in_tariff_build_year"] = int(build_period)
                n.links.at[link_name, "feed_in_tariff_active_period"] = int(active_period)
                n.links.at[link_name, "feed_in_tariff_fixed_until"] = int(build_period) + FEED_IN_TARIFF_FIXED_YEARS
                n.links.at[link_name, "feed_in_tariff_mode"] = tariff_mode

        if component_active_in_period(build_period, active_period, bhkw_lifetime):
            tariff, tariff_mode = feed_in_tariff_for_build(
                build_period, active_period, feed_in_tariff_bhkw
            )
            link_name = f"BHKW_Exportleitung_G5_{build_period}_{active_period}"
            n.add(
                "Link",
                link_name,
                bus0=bhkw_strom_bus_name(build_period),
                bus1="Überschuss_Einspeisebus",
                carrier="Strom_Strom_Einspeisung",
                p_nom=bhkw_export_capacity,
                build_year=active_period,
                lifetime=period_lifetimes[active_period],
                efficiency=1.0,
                marginal_cost=-tariff,     # Erlös = negative Kosten
            )
            n.links.at[link_name, "feed_in_tariff_eur_per_kwh"] = tariff
            n.links.at[link_name, "feed_in_tariff_build_year"] = int(build_period)
            n.links.at[link_name, "feed_in_tariff_active_period"] = int(active_period)
            n.links.at[link_name, "feed_in_tariff_fixed_until"] = int(build_period) + FEED_IN_TARIFF_FIXED_YEARS
            n.links.at[link_name, "feed_in_tariff_mode"] = tariff_mode


#%% Lasten
for i in houses:
    # Stromlast (Häuser)
    n.add(
        "Load",
        f"Stromlast_G{i}",
        bus=f"Strom_Bus_G{i}",
        carrier="Strom_Strom_Last",
        p_set=load_el_mapped[i]
    )

    # Wärmelast (Häuser)
    n.add(
        "Load",
        f"Wärmelast_G{i}",
        bus="Wärme_Bus",
        carrier="Wärme_Wärme_Last",
        p_set=load_th_mapped[i]
    )


#%% Speicherstruktur
# Stromspeicher
storage_configs = [
    {
        "name": "Stromspeicher_G1",
        "main_bus": "Strom_Bus_G1",
        "storage_bus": "Stromspeicher_Bus_G1",
        "carrier": "Strom_Strom_Speicher",
        "lifetime": storage_el_lifetime,
        "charge_efficiency": efficiency_el_storage,
        "discharge_efficiency": efficiency_el_storage,
        "standing_loss": 0.00004,
        "max_hours": max_hours_el_storage,
        "power_costs": {2025: 35, 2030: 28, 2040: 22, 2050: 18},
        "energy_costs": storage_el_cost,
        "base_power": 0.85 * peak_el_loads[1],
        "period_factors": {2025: 1.0, 2030: 1.20, 2040: 1.35, 2050: 1.55},
        "marginal_cost": 0.0005
    },
    {
        "name": "Stromspeicher_G2",
        "main_bus": "Strom_Bus_G2",
        "storage_bus": "Stromspeicher_Bus_G2",
        "carrier": "Strom_Strom_Speicher",
        "lifetime": storage_el_lifetime,
        "charge_efficiency": efficiency_el_storage,
        "discharge_efficiency": efficiency_el_storage,
        "standing_loss": 0.00004,
        "max_hours": max_hours_el_storage,
        "power_costs": {2025: 35, 2030: 28, 2040: 22, 2050: 18},
        "energy_costs": storage_el_cost,
        "base_power": 0.85 * peak_el_loads[2],
        "period_factors": {2025: 1.0, 2030: 1.20, 2040: 1.35, 2050: 1.55},
        "marginal_cost": 0.0005
    },
# Wärmespeicher
    {
        "name": "Wärmespeicher_G1",
        "main_bus": "Wärme_Bus",
        "storage_bus": "Wärmespeicher_Bus_G1",
        "carrier": "Wärme_Wärme_Speicher",
        "lifetime": storage_th_lifetime,
        "charge_efficiency": efficiency_th_storage,
        "discharge_efficiency": efficiency_th_storage,
        "standing_loss": 0.002,
        "max_hours": max_hours_th_storage,
        "power_costs": {2025: 7, 2030: 6, 2040: 5, 2050: 4},
        "energy_costs": {2025: 5, 2030: 4, 2040: 3.2, 2050: 2.5},
        "base_power": 0.65 * peak_th_loads[1],
        "period_factors": {2025: 1.0, 2030: 1.15, 2040: 1.30, 2050: 1.45},
        "marginal_cost": 0.0002
    },
    {
        "name": "Wärmespeicher_G2",
        "main_bus": "Wärme_Bus",
        "storage_bus": "Wärmespeicher_Bus_G2",
        "carrier": "Wärme_Wärme_Speicher",
        "lifetime": storage_th_lifetime,
        "charge_efficiency": efficiency_th_storage,
        "discharge_efficiency": efficiency_th_storage,
        "standing_loss": 0.002,
        "max_hours": max_hours_th_storage,
        "power_costs": {2025: 7, 2030: 6, 2040: 5, 2050: 4},
        "energy_costs": {2025: 5, 2030: 4, 2040: 3.2, 2050: 2.5},
        "base_power": 0.65 * peak_th_loads[2],
        "period_factors": {2025: 1.0, 2030: 1.15, 2040: 1.30, 2050: 1.45},
        "marginal_cost": 0.0002
    }
]

add_optimizable_storage_assets(n, storage_configs, investment_periods)
normalize_multi_investment_snapshot_index(n)


#%% CO2-Metadaten und CO2-wirksame Bezugskosten
for period in investment_periods:
    grid_name = f"Stromnetz_Bezug_{period}"
    gas_name = f"Gasnetz_Bezug_{period}"
    export_name = f"Überschuss_Einspeisung_{period}"
    chp_name = f"BHKW_G5_{period}"

# CO2-Kosten
    n.generators.at[grid_name, "marginal_cost"] = (
        marginal_cost_grid[period]
        + co2_cost_per_kwh(co2_factor_grid[period], co2_price[period])
    )
    n.generators.at[gas_name, "marginal_cost"] = (
        marginal_cost_gas[period]
        + co2_cost_per_kwh(co2_factor_gas[period], co2_price[period])
    )

# CO2-Daten an Komponenten hinterlegen
    set_component_co2_metadata(
        n, "generators", grid_name,
        co2_factor_kg_per_kwh=co2_factor_grid[period],
        co2_price_eur_per_t=co2_price[period],
        co2_port="p",
        co2_source="Stromnetz",
    )
    set_component_co2_metadata(
        n, "generators", gas_name,
        co2_factor_kg_per_kwh=0.0,
        co2_price_eur_per_t=co2_price[period],
        co2_port="p",
        co2_source="Gasnetz (Kostenbasis)",
    )
    set_component_co2_metadata(
        n, "generators", export_name,
        co2_factor_kg_per_kwh=0.0,
        co2_price_eur_per_t=co2_price[period],
        co2_port="p",
        co2_source="Export",
    )

    for house in houses:
        set_component_co2_metadata(
            n, "generators", f"PV_G{house}_{period}",
            co2_factor_kg_per_kwh=0.0,
            co2_price_eur_per_t=co2_price[period],
            co2_port="p",
            co2_source="PV",
        )

    for house in heat_pump_houses:
        set_component_co2_metadata(
            n, "links", f"Wärmepumpe_G{house}_{period}",
            co2_factor_kg_per_kwh=0.0,
            co2_price_eur_per_t=co2_price[period],
            co2_port="p0",
            co2_source="Strommix wird upstream bilanziert",
        )

    set_component_co2_metadata(
        n, "links", chp_name,
        co2_factor_kg_per_kwh=co2_factor_gas[period],
        co2_price_eur_per_t=co2_price[period],
        co2_port="p0",
        co2_source="Gas",
    )

for link_name, source_name in [
    *[(name, "PV-Export") for name in n.links.index if str(name).startswith("PV_Exportleitung_")],
    *[(name, "BHKW-Export") for name in n.links.index if str(name).startswith("BHKW_Exportleitung_")],
    *[(name, "PV intern") for name in n.links.index if str(name).startswith("PV_Stromnutzung_")],
    *[(name, "BHKW intern") for name in n.links.index if str(name).startswith("BHKW_Stromnutzung_")],
    *[(name, "Quartiersleitung") for name in n.links.index if str(name).startswith("Quartiersleitung_")],
]:
    set_component_co2_metadata(
        n, "links", link_name,
        co2_factor_kg_per_kwh=0.0,
        co2_price_eur_per_t=0.0,
        co2_port="p0",
        co2_source=source_name,
    )

for cfg in storage_configs:
    for period in investment_periods:
        for link_name in [f"{cfg['name']}_Laden_{period}", f"{cfg['name']}_Entladen_{period}"]:
            set_component_co2_metadata(
                n, "links", link_name,
                co2_factor_kg_per_kwh=0.0,
                co2_price_eur_per_t=0.0,
                co2_port="p0",
                co2_source="Speicher",
            )


#%% Optimierung
optimize_with_multiindex_storage_fix(
    n,
    solver_name="gurobi",
    multi_investment_periods=True,
    include_objective_constant=False,
    extra_functionality=couple_gas_grid_to_chp_capacity,
)

apply_system_geo_metadata(n, investment_periods)


#%% Finanzmetadaten für Dashboard-Export
for period in investment_periods:
    grid_name = f"Stromnetz_Bezug_{period}"
    gas_name = f"Gasnetz_Bezug_{period}"
    export_name = f"Überschuss_Einspeisung_{period}"
    chp_name = f"BHKW_G5_{period}"

# Investitionskosten Anlagen
    for gen_name in [grid_name, gas_name, export_name]:
        set_component_financial_metadata(
            n, "generators", gen_name,
            capital_cost_overnight=0.0,
            discount_rate=DISCOUNT_RATE,
            fixed_cost=0.0,
        )

    for house in houses:
        set_component_financial_metadata(
            n, "generators", f"PV_G{house}_{period}",
            capital_cost_overnight=pv_cost[period],
            discount_rate=DISCOUNT_RATE,
            fixed_cost=0.0,
        )

    for house in heat_pump_houses:
        set_component_financial_metadata(
            n, "links", f"Wärmepumpe_G{house}_{period}",
            capital_cost_overnight=wp_cost[period],
            discount_rate=DISCOUNT_RATE,
            fixed_cost=0.0,
        )

    set_component_financial_metadata(
        n, "links", chp_name,
        capital_cost_overnight=bhkw_cost[period] * efficiency_el_bhkw,
        discount_rate=DISCOUNT_RATE,
        fixed_cost=0.0,
    )

for link_name in [
    *[name for name in n.links.index if str(name).startswith("PV_Exportleitung_")],
    *[name for name in n.links.index if str(name).startswith("BHKW_Exportleitung_")],
    *[name for name in n.links.index if str(name).startswith("PV_Stromnutzung_")],
    *[name for name in n.links.index if str(name).startswith("BHKW_Stromnutzung_")],
    *[name for name in n.links.index if str(name).startswith("Quartiersleitung_")],
]:
    set_component_financial_metadata(
        n, "links", link_name,
        capital_cost_overnight=0.0,
        discount_rate=DISCOUNT_RATE,
        fixed_cost=0.0,
    )

# Speicher
for cfg in storage_configs:
    for period in investment_periods:
        charge_name = f"{cfg['name']}_Laden_{period}"
        discharge_name = f"{cfg['name']}_Entladen_{period}"
        storage_name = f"{cfg['name']}_{period}"

# Leistungskosten Links
        set_component_financial_metadata(
            n, "links", charge_name,
            capital_cost_overnight=cfg["power_costs"][period],
            discount_rate=DISCOUNT_RATE,
            fixed_cost=0.0,
        )
        set_component_financial_metadata(
            n, "links", discharge_name,
            capital_cost_overnight=cfg["power_costs"][period],
            discount_rate=DISCOUNT_RATE,
            fixed_cost=0.0,
        )
        set_component_financial_metadata(
            n, "storage_units", storage_name,
            capital_cost_overnight=cfg["energy_costs"][period] * cfg["max_hours"],
            discount_rate=DISCOUNT_RATE,
            fixed_cost=0.0,
        )

if not hasattr(n, "meta") or n.meta is None:
    n.meta = {}
n.meta["economic_discount_rate"] = DISCOUNT_RATE
n.meta["co2_costs_in_marginal_cost"] = True


#%% Exportieren
export_path = BASE_DIR / "Quartiersystem_con_ees.nc"
export_network_safely(n, export_path)
