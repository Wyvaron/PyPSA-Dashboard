# -*- coding: utf-8 -*-
"""
Grundsystem

Erzeugt ein Multi-Investment-Period-PyPSA-Netzwerk für das Grundsystem.
Neben der Optimierungsstruktur werden Kosten-, CO2- und Kartenmetadaten
gespeichert, die das Dashboard später direkt aus der .nc-Datei ausliest.

@author: joshua
"""

from pathlib import Path

import pandas as pd
import pypsa

BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd().resolve()

DISCOUNT_RATE = 0.05

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
    "Stromnetz-Bezug": (6.98656, 50.93571),
    "Fernwärme-Bezug": (6.98712, 50.93639),
    "Gasnetz-Bezug": (6.98769, 50.93644),
    "Überschuss-Einspeisung": (6.98656, 50.93571),
    "Solarthermie": (6.98803, 50.93571),
    "Gaskessel": (6.98792, 50.93385),
    "Wärmepumpe": (6.98792, 50.93360),
    "BHKW": (6.98767, 50.93377),
    "Stromlast": (6.98852, 50.93389),
    "Wärmelast": (6.98940, 50.93404),
    "PV": (6.98735, 50.93435),
    "Stromspeicher": (6.98759, 50.93410),
    "Wärmespeicher": (6.98947, 50.93355),
    "Gasspeicher": (6.98705, 50.93597),
}

# Verknüpft PyPSA-Komponenten mit Kartenlabels und Koordinatenschlüsseln.
MAP_COMPONENT_GEO = [
    ("generators", "prefix", "Stromnetz_Bezug_", "Stromnetz-Bezug", "Stromnetz-Bezug"),
    ("generators", "prefix", "Fernwärme_Bezug_", "Fernwärme-Bezug", "Fernwärme-Bezug"),
    ("generators", "prefix", "Gasnetz_Bezug_", "Gasnetz-Bezug", "Gasnetz-Bezug"),
    ("generators", "prefix", "Überschuss_Einspeisung_", "Überschuss-Einspeisung", "Überschuss-Einspeisung"),
    ("generators", "prefix", "Solarthermie_", "Solarthermie", "Solarthermie"),
    ("links", "period", "Gaskessel_{period}", "Gaskessel {period}", "Gaskessel"),
    ("links", "period", "Wärmepumpe_{period}", "Wärmepumpe {period}", "Wärmepumpe"),
    ("links", "period", "BHKW_{period}", "BHKW {period}", "BHKW"),
    ("loads", "exact", "Stromlast", "Stromlast", "Stromlast"),
    ("loads", "exact", "Wärmelast", "Wärmelast", "Wärmelast"),
    ("generators", "period", "PV_{period}", "PV {period}", "PV"),
    ("links", "period", "Stromspeicher_Laden_{period}", "Stromspeicher Laden {period}", "Stromspeicher"),
    ("links", "period", "Stromspeicher_Entladen_{period}", "Stromspeicher Entladen {period}", "Stromspeicher"),
    ("storage_units", "period", "Stromspeicher_{period}", "Stromspeicher {period}", "Stromspeicher"),
    ("links", "period", "Wärmespeicher_Laden_{period}", "Wärmespeicher Laden {period}", "Wärmespeicher"),
    ("links", "period", "Wärmespeicher_Entladen_{period}", "Wärmespeicher Entladen {period}", "Wärmespeicher"),
    ("storage_units", "period", "Wärmespeicher_{period}", "Wärmespeicher {period}", "Wärmespeicher"),
    ("links", "period", "Gasspeicher_Laden_{period}", "Gasspeicher Laden {period}", "Gasspeicher"),
    ("links", "period", "Gasspeicher_Entladen_{period}", "Gasspeicher Entladen {period}", "Gasspeicher"),
    ("storage_units", "period", "Gasspeicher_{period}", "Gasspeicher {period}", "Gasspeicher"),
]


def pv_bus_name(period):
    """
    Erzeugt den periodenspezifischen Busnamen für die PV-Anbindung.

    Inputs: Investitionsperiode.
    Outputs: Busname als String.
    """
    return f"PV_Strom_Bus_{int(period)}"


def bhkw_strom_bus_name(period):
    """
    Erzeugt den periodenspezifischen Strombusnamen für das BHKW.

    Inputs: Investitionsperiode.
    Outputs: Busname als String.
    """
    return f"BHKW_Strom_Bus_{int(period)}"


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
def read_profile(filename, value_column):
    """
    Liest ein Einzelprofil ein und bereitet Zeitindex und Zahlenwerte auf.

    Inputs: Dateiname und Spalte, die als numerische Zeitreihe genutzt wird.
    Outputs: sortierter DataFrame mit DatetimeIndex.
    """
    profile_path = BASE_DIR / filename
    df = pd.read_csv(
        profile_path,
        sep=";",
        decimal=",",
        parse_dates=["date"],
        dayfirst=True
    ).set_index("date")
    df.index = pd.to_datetime(df.index, errors="coerce")
    df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    return df.sort_index()

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
    return pd.MultiIndex.from_tuples(arrays, names=["period", "snapshot"])

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
            names=["period", "snapshot"],
        )
        blocks.append(shifted)
    return pd.concat(blocks)

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
    if getattr(current_expand_series, "_grundsystem_multiindex_patch", False):
        return

    original_expand_series = getattr(
        current_expand_series,
        "_grundsystem_original_expand_series",
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

    expand_series_with_named_snapshot_index._grundsystem_multiindex_patch = True
    expand_series_with_named_snapshot_index._grundsystem_original_expand_series = original_expand_series
    pypsa_common.expand_series = expand_series_with_named_snapshot_index
    pypsa_constraints.expand_series = expand_series_with_named_snapshot_index


def optimize_with_multiindex_storage_fix(network, **kwargs):
    """
    Startet die PyPSA-Optimierung mit vorheriger MultiIndex-Korrektur.

    Inputs: PyPSA-Netzwerk und Optimierungsargumente.
    Outputs: Ergebnis von network.optimize.
    """
    patch_pypsa_expand_series_for_multiindex_snapshots()
    return network.optimize(**kwargs)


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
    network.meta["spatial_lineage"] = "Konzeptionelle Standortzuordnung im Grundsystem.py"

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
                marginal_cost=0.0,
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
                marginal_cost=0.0,
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
                marginal_cost=cfg.get("marginal_cost", 0.0),
            )

#%% Profile einlesen
load_el = read_profile("load_el.csv", "P_el")
load_th = read_profile("load_th.csv", "Q_htg")
pv_gen = read_profile("pv_gen.csv", "P_pv")

# Erstellen der Datumsstruktur
common_index = load_el.index.intersection(load_th.index).intersection(pv_gen.index).sort_values()
load_el = load_el.reindex(common_index)
load_th = load_th.reindex(common_index)
pv_gen = pv_gen.reindex(common_index)

# Von Wh/Tag zu kW
load_el["P_el"] = load_el["P_el"] / 24 / 1000
load_th["Q_htg"] = load_th["Q_htg"] / 24 / 1000
pv_gen["P_pv"] = pv_gen["P_pv"] / 24 / 1000

# Skalierung der Profile auf ein passendes Niveau
electricity_load_scale = 1.15
heat_load_scale = 1.30
load_el["P_el"] *= electricity_load_scale
load_th["Q_htg"] *= heat_load_scale

# Solarthermie nutzt gleiche Saisonalität wie PV
load_th["P_solar"] = pv_gen["P_pv"].reindex(load_th.index) * 1.2


#%% Dashboard-taugliche Zeitauflösung
USE_WEEKLY_RESOLUTION = False

if USE_WEEKLY_RESOLUTION:
    load_el = load_el.resample("W-MON").mean()
    load_th = load_th.resample("W-MON").mean()
    pv_gen = pv_gen.resample("W-MON").mean()


#%% Variablen
investment_periods = [2025, 2030, 2040, 2050]
multi_invest_snapshots = build_multi_invest_snapshots(load_el.index, investment_periods)

# Effizienzen
efficiency_gaskessel = 1.08
efficiency_th_bhkw = 0.50
efficiency_el_bhkw = 0.35
efficiency_cop_wp = 4.5
efficiency_th_storage = 0.90
efficiency_el_storage = 0.95
efficiency_gas_storage = 0.95

# Leistungen
p_nom_max_bhkw = 90.0                            # kW
p_nom_min_bhkw = 0.0                             # kW

# Preisentwicklungen
wp_cost = {2025: 1900, 2030: 1750, 2040: 1550, 2050: 1400}        # €/kW_el
pv_cost = {2025: 1250, 2030: 1150, 2040: 1050, 2050: 950}          # €/kW_el
solar_cost = {2025: 780, 2030: 730, 2040: 680, 2050: 630}        # €/kW_th
bhkw_cost = {2025: 1700, 2030: 1750, 2040: 1850, 2050: 2000}     # €/kW_el
gaskessel_cost = {2025: 120, 2030: 130, 2040: 150, 2050: 180}    # €/kW_th
storage_el_cost = {2025: 600, 2030: 520, 2040: 460, 2050: 400}   # €/kWh_el
storage_th_cost = {2025: 12, 2030: 11, 2040: 10, 2050: 9}         # €/kWh_th
storage_gas_cost = {2025: 4.5, 2030: 4.3, 2040: 4.0, 2050: 3.8}  # €/kWh
co2_price = {2025: 55, 2030: 100, 2040: 160, 2050: 220}          # €/t
co2_factor_grid = {2025: 0.36, 2030: 0.2, 2040: 0.08, 2050: 0}   # kg/kWh
co2_factor_heat = {2025: 0.28, 2030: 0.2, 2040: 0.1, 2050: 0.05} # kg/kWh
co2_factor_gas = {2025: 0.2, 2030: 0.2, 2040: 0.2, 2050: 0.2}    # kg/kWh

# Lebensdauern
wp_lifetime = 15                               # Jahre
pv_lifetime = 25                               # Jahre
solar_lifetime = 20                            # Jahre
bhkw_lifetime = 10                             # Jahre
gaskessel_lifetime = 15                        # Jahre
storage_el_lifetime = 15                       # Jahre
storage_th_lifetime = 20                       # Jahre
storage_gas_lifetime = 20                      # Jahre

# Energiekosten
marginal_cost_grid = {2025: 0.30, 2030: 0.34, 2040: 0.39, 2050: 0.44}       # €/kWh
marginal_cost_gas = {2025: 0.11, 2030: 0.12, 2040: 0.15, 2050: 0.18}        # €/kWh
marginal_cost_heat_grid = {2025: 0.17, 2030: 0.19, 2040: 0.21, 2050: 0.23}  # €/kWh

# Einspeisung (Strom)
feed_in_tariff_pv = {2025: 0.06, 2030: 0.04, 2040: 0.03, 2050: 0.02}        # €/kWh
feed_in_tariff_bhkw = {2025: 0.08, 2030: 0.075, 2040: 0.07, 2050: 0.065}      # €/kWh
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
max_hours_gas_storage = 72.0

# Ermitteln der Spitzenlast
peak_el_load = float(load_el["P_el"].max())
peak_th_load = float(load_th["Q_htg"].max())
peak_gas_proxy = max(peak_th_load / efficiency_gaskessel, 1.0)

# Begrenzung der Erzeugungs-Leistung
p_nom_max_pv = 320.0
p_nom_max_solar = 240.0
p_nom_max_wp = 260.0
p_nom_max_gaskessel = 280.0


# Begrenzung der Leistungsflüsse
free_transfer_capacity = max(
    2.0 * peak_el_load,
    p_nom_max_pv,
    p_nom_max_bhkw,
    180.0,
)
pv_export_capacity = 0.35 * p_nom_max_pv
bhkw_export_capacity = 0.45 * p_nom_max_bhkw
combined_export_capacity = pv_export_capacity + bhkw_export_capacity
bezugsleistung_tie_breaker_cost = 1e-9


#%% Netzwerk
n = pypsa.Network()

# Investitionsperioden setzen
n.set_investment_periods(investment_periods)
n.set_snapshots(multi_invest_snapshots)

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
pv_shape = pv_gen["P_pv"] / pv_gen["P_pv"].max()
solar_shape = load_th["P_solar"] / load_th["P_solar"].max()

# Verhindert einen überprotortionalen PV-Zubau
pv_shape *= min(1.0, 0.11 / pv_shape.mean())
solar_shape *= min(1.0, 0.14 / solar_shape.mean())

# kopiert die Zeitreihe für alle Investitionsjahre
pv_pu = expand_series_to_period_snapshots(pv_shape.clip(lower=0.0, upper=1.0), investment_periods)
solar_pu = expand_series_to_period_snapshots(solar_shape.clip(lower=0.0, upper=1.0), investment_periods)
load_el_mapped = expand_series_to_period_snapshots(load_el["P_el"], investment_periods)
load_th_mapped = expand_series_to_period_snapshots(load_th["Q_htg"], investment_periods)


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
    "Wärme_Wärme_Netzbezug",
    "Wärme_Wärme_Solarthermie",
    "Wärme_Wärme_Speicher",
    "Wärme_Wärme_Last",
    "Wärme_Wärme_Gas",
    "Wärme_Wärme_Gasnetz",
    "Wärme_Wärme_Gasspeicher"
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
n.add("Bus", "Stromspeicher_Bus", carrier="Strom_Strom_Speicher")
n.add("Bus", "Wärmespeicher_Bus", carrier="Wärme_Wärme_Speicher")
n.add("Bus", "Gasspeicher_Bus", carrier="Wärme_Wärme_Gasspeicher")
n.add("Bus", "Überschuss_Einspeisebus", carrier="Strom_Strom_Einspeisung")
for period in investment_periods:
    n.add("Bus", pv_bus_name(period), carrier="Strom_Strom_PV")
    n.add("Bus", bhkw_strom_bus_name(period), carrier="Strom_Strom_BHKW")


#%% Generatoren
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

    # Fernwärme
    n.add(
        "Generator",
        f"Fernwärme_Bezug_{period}",
        bus="Wärme_Bus",
        carrier="Wärme_Wärme_Netzbezug",
        p_nom_extendable=True,
        p_nom_min=0.0,
        p_nom_max=180.0,
        build_year=period,
        lifetime=period_lifetimes[period],
        capital_cost=bezugsleistung_tie_breaker_cost,
        marginal_cost=marginal_cost_heat_grid[period]  # €/kWh_th
    )

    # Gasnetz
    n.add(
        "Generator",
        f"Gasnetz_Bezug_{period}",
        bus="Gas_Bus",
        carrier="Wärme_Wärme_Gasnetz",
        p_nom_extendable=True,
        p_nom_min=0.0,
        p_nom_max=p_nom_max_gaskessel,
        build_year=period,
        lifetime=period_lifetimes[period],
        capital_cost=bezugsleistung_tie_breaker_cost,
        marginal_cost=marginal_cost_gas[period]       # €/kWh
    )

    # Gemeinsamer negativer Generator für PV- und BHKW-Überschussstrom
    n.add(
        "Generator",
        f"Überschuss_Einspeisung_{period}",
        bus="Überschuss_Einspeisebus",
        carrier="Strom_Strom_Einspeisung",
        sign=-1.0,
        p_nom=combined_export_capacity,
        build_year=period,
        lifetime=period_lifetimes[period],
        marginal_cost=0.0
    )

    # PV
    n.add(
        "Generator",
        f"PV_{period}",
        bus=pv_bus_name(period),
        carrier="Strom_Strom_PV",
        p_nom_extendable=True,
        p_nom_max=p_nom_max_pv,
        build_year=period,
        lifetime=pv_lifetime,
        capital_cost=annualized_cost(pv_cost[period], pv_lifetime),         # nach Investitionsperiode (€/kW_el)
        marginal_cost=0.0,
        p_max_pu=pv_pu
    )
    
    # Solarthermie
    n.add(
        "Generator",
        f"Solarthermie_{period}",
        bus="Wärme_Bus",
        carrier="Wärme_Wärme_Solarthermie",
        p_nom_extendable=True,
        p_nom_max=p_nom_max_solar,
        build_year=period,
        lifetime=solar_lifetime,
        capital_cost=annualized_cost(solar_cost[period], solar_lifetime),   # nach Investitionsperiode (€/kW_th)
        marginal_cost=0.0,
        p_max_pu=solar_pu
    )
    
#%% Links
    # Gaskessel
    n.add(
        "Link",
        f"Gaskessel_{period}",
        bus0="Gas_Bus",
        bus1="Wärme_Bus",
        carrier="Wärme_Wärme_Gas",
        p_nom_extendable=True,
        p_nom_min=0.0,
        p_nom_max=p_nom_max_gaskessel,
        build_year=period,
        lifetime=gaskessel_lifetime,
        efficiency=efficiency_gaskessel,
        capital_cost=annualized_cost(gaskessel_cost[period] * efficiency_gaskessel, gaskessel_lifetime), # €/kW_th auf Link-Eingangsleistung umgerechnet
        marginal_cost=0.0
    )
    
    # Wärmepumpe
    n.add(
        "Link",
        f"Wärmepumpe_{period}",
        bus0="Strom_Bus",
        bus1="Wärme_Bus",
        carrier="Strom_Strom",
        p_nom_extendable=True,
        p_nom_min=0.0,
        p_nom_max=p_nom_max_wp,
        build_year=period,
        lifetime=wp_lifetime,
        efficiency=efficiency_cop_wp,
        capital_cost=annualized_cost(wp_cost[period], wp_lifetime),               # nach Investitionsperiode (€/kW_el)
        marginal_cost=0.0
    )
    
    # BHKW
    n.add(
        "Link",
        f"BHKW_{period}",
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

# Stromnutzung und Einspeisung je Anlagenjahrgang
for build_period in investment_periods:
    n.add(
        "Link",
        f"PV_Stromnutzung_{build_period}",
        bus0=pv_bus_name(build_period),
        bus1="Strom_Bus",
        carrier="Strom_Strom_PV",
        p_nom=free_transfer_capacity,
        build_year=build_period,
        lifetime=pv_lifetime,
        efficiency=1.0,
        marginal_cost=0.0,
    )

    n.add(
        "Link",
        f"BHKW_Stromnutzung_{build_period}",
        bus0=bhkw_strom_bus_name(build_period),
        bus1="Strom_Bus",
        carrier="Strom_Strom_BHKW",
        p_nom=free_transfer_capacity,
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
            link_name = f"PV_Exportleitung_{build_period}_{active_period}"
            n.add(
                "Link",
                link_name,
                bus0=pv_bus_name(build_period),
                bus1="Überschuss_Einspeisebus",
                carrier="Strom_Strom_Einspeisung",
                p_nom=pv_export_capacity,
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
            link_name = f"BHKW_Exportleitung_{build_period}_{active_period}"
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
n.add(
    "Load",
    "Stromlast",
    bus="Strom_Bus",
    carrier="Strom_Strom_Last",
    p_set=load_el_mapped
)
n.add(
    "Load",
    "Wärmelast",
    bus="Wärme_Bus",
    carrier="Wärme_Wärme_Last",
    p_set=load_th_mapped
)

#%% Speicherstruktur
# Stromspeicher
storage_configs = [
    {
        "name": "Stromspeicher",
        "main_bus": "Strom_Bus",
        "storage_bus": "Stromspeicher_Bus",
        "carrier": "Strom_Strom_Speicher",
        "lifetime": storage_el_lifetime,
        "charge_efficiency": efficiency_el_storage,
        "discharge_efficiency": efficiency_el_storage,
        "standing_loss": 0.00004,                       # 0.004 % Verlust pro Stunde
        "max_hours": max_hours_el_storage,
        "power_costs": {2025: 35, 2030: 28, 2040: 22, 2050: 18},
        "energy_costs": storage_el_cost,
        "base_power": 0.85 * peak_el_load,
        "period_factors": {2025: 1.0, 2030: 1.20, 2040: 1.35, 2050: 1.55},
        "marginal_cost": 0.0005,
    },

# Wärmespeicher
    {
        "name": "Wärmespeicher",
        "main_bus": "Wärme_Bus",
        "storage_bus": "Wärmespeicher_Bus",
        "carrier": "Wärme_Wärme_Speicher",
        "lifetime": storage_th_lifetime,
        "charge_efficiency": efficiency_th_storage,
        "discharge_efficiency": efficiency_th_storage,
        "standing_loss": 0.002,                         # 0.2 % Verlust pro Stunde
        "max_hours": max_hours_th_storage,
        "power_costs": {2025: 7, 2030: 6, 2040: 5, 2050: 4},
        "energy_costs": {2025: 5, 2030: 4, 2040: 3.2, 2050: 2.5},
        "base_power": 0.65 * peak_th_load,
        "period_factors": {2025: 1.0, 2030: 1.15, 2040: 1.30, 2050: 1.45},
        "marginal_cost": 0.0002,
    },

# Gasspeicher
    {
        "name": "Gasspeicher",
        "main_bus": "Gas_Bus",
        "storage_bus": "Gasspeicher_Bus",
        "carrier": "Wärme_Wärme_Gasspeicher",
        "lifetime": storage_gas_lifetime,
        "charge_efficiency": efficiency_gas_storage,
        "discharge_efficiency": efficiency_gas_storage,
        "standing_loss": 0.0,                           # kein Verlust pro Stunde
        "max_hours": max_hours_gas_storage,
        "power_costs": {2025: 4, 2030: 3.5, 2040: 3.0, 2050: 2.5},
        "energy_costs": {2025: 2.5, 2030: 2.2, 2040: 2.0, 2050: 1.8},
        "base_power": 0.45 * peak_gas_proxy,
        "period_factors": {2025: 1.0, 2030: 1.10, 2040: 1.20, 2050: 1.30},
        "marginal_cost": 0.0001,
    },
]

add_optimizable_storage_assets(n, storage_configs, investment_periods)


#%% CO2-Metadaten und CO2-wirksame Bezugskosten
for period in investment_periods:
    grid_name = f"Stromnetz_Bezug_{period}"
    heat_name = f"Fernwärme_Bezug_{period}"
    gas_name = f"Gasnetz_Bezug_{period}"
    export_name = f"Überschuss_Einspeisung_{period}"
    pv_name = f"PV_{period}"
    solar_name = f"Solarthermie_{period}"
    boiler_name = f"Gaskessel_{period}"
    hp_name = f"Wärmepumpe_{period}"
    chp_name = f"BHKW_{period}"

# CO2-Kosten
    n.generators.at[grid_name, "marginal_cost"] = (
        marginal_cost_grid[period]
        + co2_cost_per_kwh(co2_factor_grid[period], co2_price[period])
    )
    n.generators.at[heat_name, "marginal_cost"] = (
        marginal_cost_heat_grid[period]
        + co2_cost_per_kwh(co2_factor_heat[period], co2_price[period])
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
        n, "generators", heat_name,
        co2_factor_kg_per_kwh=co2_factor_heat[period],
        co2_price_eur_per_t=co2_price[period],
        co2_port="p",
        co2_source="Fernwärme",
    )
    set_component_co2_metadata(
        n, "generators", gas_name,
        co2_factor_kg_per_kwh=0.0,
        co2_price_eur_per_t=co2_price[period],
        co2_port="p",
        co2_source="Gasnetz (Kostenbasis)",
    )

    for gen_name, source_name in [
        (export_name, "Export"),
        (pv_name, "PV"),
        (solar_name, "Solarthermie"),
    ]:
        set_component_co2_metadata(
            n, "generators", gen_name,
            co2_factor_kg_per_kwh=0.0,
            co2_price_eur_per_t=co2_price[period],
            co2_port="p",
            co2_source=source_name,
        )

    set_component_co2_metadata(
        n, "links", boiler_name,
        co2_factor_kg_per_kwh=co2_factor_gas[period],
        co2_price_eur_per_t=co2_price[period],
        co2_port="p0",
        co2_source="Gas",
    )
    set_component_co2_metadata(
        n, "links", hp_name,
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
]:
    set_component_co2_metadata(
        n, "links", link_name,
        co2_factor_kg_per_kwh=0.0,
        co2_price_eur_per_t=0.0,
        co2_port="p0",
        co2_source=source_name,
    )


#%% Optimierung
optimize_with_multiindex_storage_fix(
    n,
    solver_name="gurobi",
    multi_investment_periods=True,
    include_objective_constant=False,
)

apply_system_geo_metadata(n, investment_periods)


#%% Finanzmetadaten für Dashboard-Export
for period in investment_periods:
    grid_name = f"Stromnetz_Bezug_{period}"
    heat_name = f"Fernwärme_Bezug_{period}"
    gas_name = f"Gasnetz_Bezug_{period}"
    export_name = f"Überschuss_Einspeisung_{period}"
    pv_name = f"PV_{period}"
    solar_name = f"Solarthermie_{period}"
    boiler_name = f"Gaskessel_{period}"
    hp_name = f"Wärmepumpe_{period}"
    chp_name = f"BHKW_{period}"

# Investitionskosten Anlagen
    for gen_name in [grid_name, heat_name, gas_name, export_name]:
        set_component_financial_metadata(
            n, "generators", gen_name,
            capital_cost_overnight=0.0,
            discount_rate=DISCOUNT_RATE,
            fixed_cost=0.0,
        )

    set_component_financial_metadata(
        n, "generators", pv_name,
        capital_cost_overnight=pv_cost[period],
        discount_rate=DISCOUNT_RATE,
        fixed_cost=0.0,
    )
    set_component_financial_metadata(
        n, "generators", solar_name,
        capital_cost_overnight=solar_cost[period],
        discount_rate=DISCOUNT_RATE,
        fixed_cost=0.0,
    )
    set_component_financial_metadata(
        n, "links", boiler_name,
        capital_cost_overnight=gaskessel_cost[period] * efficiency_gaskessel,
        discount_rate=DISCOUNT_RATE,
        fixed_cost=0.0,
    )
    set_component_financial_metadata(
        n, "links", hp_name,
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
export_path = BASE_DIR / "Grundsystem_con_ees.nc"
export_network_safely(n, export_path)
