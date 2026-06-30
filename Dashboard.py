# -*- coding: utf-8 -*-
"""
Dynamic PyPSA Dashboard

Liest optimierte PyPSA-Netzwerke aus NetCDF-Dateien ein, erzeugt daraus einen
zentralen Auswertungszustand und stellt technische, ökologische,
wirtschaftliche sowie räumliche Kennzahlen in einer Dash-Oberfläche dar.
"""


# %% Imports
import io
import os
import re
import ast
import json
import math
import unicodedata
from html import escape as html_escape
from datetime import datetime
from functools import lru_cache
from collections import Counter

import pypsa
import numpy as np
import pandas as pd

from dash import Dash, html, dcc, ctx, no_update
from dash.dependencies import Input, Output, State

import plotly.express as px
import plotly.graph_objects as go

import threading
import traceback
import copy
import plotly.io as pio

# Basistemplate beibehalten und auf die im Dashboard verwendete Typografie anpassen.
pio.templates["plotly_ari"] = copy.deepcopy(pio.templates["plotly"])
pio.templates["plotly_ari"].layout.font.family = "Open Sans, Arial, sans-serif"
pio.templates["plotly_ari"].layout.font.size = 16
pio.templates["plotly_ari"].layout.title.font.family = "Lora, Georgia, serif"
pio.templates["plotly_ari"].layout.title.font.size = 19
pio.templates["plotly_ari"].layout.separators = ",."
pio.templates.default = "plotly_ari"

HEADING_FONT_FAMILY = "Lora, Georgia, serif"
BODY_FONT_FAMILY = "Open Sans, Arial, sans-serif"
BASE_FONT_SIZE_PX = 16
TITLE_FONT_SIZE_PX = 19
CHART_EPS = 1e-9
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
OSM_ATTRIBUTION_TEXT = f"Kartendaten © OpenStreetMap-Mitwirkende ({OSM_COPYRIGHT_URL})"

# Einheitliche Farbsemantik: gleiche Kennzahlen und Technologien behalten über alle Module hinweg dieselbe Grundfarbe.
SEMANTIC_COLORS = {
    "Strom": "#2F6F9F",
    "Wärme": "#C45A3D",
    "Wärme_Netzbezug": "#1B9E77",
    "Wärme_Speicher": "#7A4FB3",
    "Gas": "#8A6F3D",
    "PV": "#F0B429",
    "PV-Erzeugung": "#F2B705",
    "PV-Eigenverbrauch": "#2E7D32",
    "PV-Einspeisung": "#2D9CDB",
    "Strombezug": "#264653",
    "Solarthermie": "#E08D2D",
    "BHKW": "#5B6BB8",
    "Wärmepumpe": "#2A9D8F",
    "Gaskessel": "#8A6F3D",
    "Fernwärme": "#49A6A6",
    "Fernwärmebezug": "#49A6A6",
    "Gasnetzbezug": "#8A6F3D",
    "Stromnetz_Bezug": "#2F6F9F",
    "Netzbezug": "#9ACD3C",
    "Einspeisung": "#4FB99F",
    "Stromspeicher": "#7A4FB3",
    "Wärmespeicher": "#C45A9D",
    "Gasspeicher": "#6D8F38",
    "CAPEX": "#E68600",
    "OPEX": "#5B6BB8",
    "CO2": "#2A7F73",
    "Kumuliert": "#C45A9D",
    "Vorteil": "#2CA02C",
    "Nachteil": "#D62728",
    "Sonstige": "#7A7A7A",
}


# Globale Regeln für Typografie, Ladehinweise, Dropdown-Ebenen und die fixierten Filterbereiche der einzelnen Registerkarten.
GLOBAL_DASHBOARD_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Lora:wght@500;600;700&family=Open+Sans:wght@400;600;700&display=swap');
body, .dash-dropdown, .Select, .Select-control, .Select-menu-outer {{
  font-family: {BODY_FONT_FAMILY};
  font-size: {BASE_FONT_SIZE_PX}px;
}}
#datafile-dropdown, #datafile-dropdown .Select, #datafile-dropdown .Select-control {{
  position: relative;
  z-index: 5000;
}}
#datafile-dropdown .Select-menu-outer {{
  z-index: 5001 !important;
}}
h1, h2, h3, h4, h5, h6, .tab, .dash-tab, .dash-tabs, .map-title {{
  font-family: {HEADING_FONT_FAMILY};
}}
h2 {{ font-size: 24px; }}
h3 {{ font-size: 19px; margin-top: 18px; }}
h4 {{ font-size: 18px; }}
.dashboard-note {{
  font-family: {BODY_FONT_FAMILY};
  color: #536471;
  font-size: {BASE_FONT_SIZE_PX}px;
  line-height: 1.4;
  margin: 4px 0 12px 0;
}}
.info-box {{
  border: 1px solid #d8dee6;
  border-left: 4px solid #2f6f9f;
  background: #f8fafc;
  color: #334155;
  padding: 12px 14px;
  border-radius: 6px;
  margin: 8px 0 14px 0;
  font-family: {BODY_FONT_FAMILY};
  font-size: {BASE_FONT_SIZE_PX}px;
  line-height: 1.4;
}}
.register-agenda {{
  border: 1px solid #d8dee6;
  border-left: 4px solid #2f6f9f;
  background: #f8fafc;
  color: #334155;
  padding: 12px 14px;
  border-radius: 6px;
  margin: 4px 0 18px 0;
  font-family: {BODY_FONT_FAMILY};
  font-size: {BASE_FONT_SIZE_PX}px;
  line-height: 1.4;
}}
.register-agenda-title {{
  font-family: {BODY_FONT_FAMILY};
  font-size: {BASE_FONT_SIZE_PX}px;
  font-weight: 600;
  color: #0f3554;
  margin-bottom: 8px;
}}
.register-agenda-list {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}}
.register-agenda-link {{
  display: inline-block;
  padding: 5px 9px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  background: #ffffff;
  color: #0f3554;
  text-decoration: none;
  font-size: {BASE_FONT_SIZE_PX}px;
  line-height: 1.3;
}}
.register-agenda-link:hover {{
  border-color: #2f6f9f;
  color: #2f6f9f;
  text-decoration: underline;
}}
.diagram-anchor, .scroll-anchor {{
  scroll-margin-top: 205px;
}}
html {{
  scroll-behavior: smooth;
}}
[data-dash-is-loading="true"]::after {{
  content: "Daten werden geladen...";
  position: fixed;
  z-index: 99999;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  padding: 74px 26px 24px 26px;
  min-width: 240px;
  text-align: center;
  color: #0f3554;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #d8dee6;
  border-radius: 10px;
  box-shadow: 0 12px 34px rgba(15, 53, 84, 0.22);
  font-family: {BODY_FONT_FAMILY};
  font-size: 17px;
  font-weight: 600;
}}
[data-dash-is-loading="true"]::before {{
  content: "";
  position: fixed;
  z-index: 100000;
  top: calc(50% - 48px);
  left: calc(50% - 22px);
  width: 44px;
  height: 44px;
  border: 5px solid #dbe5ef;
  border-top-color: #2f6f9f;
  border-radius: 50%;
  animation: dashboard-spin 0.9s linear infinite;
}}
@keyframes dashboard-spin {{
  to {{ transform: rotate(360deg); }}
}}
"""

# %% Konfiguration: Datenverzeichnis + Cachegröße

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Pfad für die .nc-Dateien
DATA_DIR = BASE_DIR

# LRU Cache: wie viele Datasets (inkl. pypsa.Network + abgeleitete Tabellen/Figuren) gleichzeitig gehalten werden
LRU_CACHE_SIZE = 4

# Globaler Lock für mehr Stabilität
_STATE_BUILD_LOCK = threading.Lock()

#%% Carrier/Subcarrier Taxonomie

CARRIER_SEP = "_"
DEFAULT_SUBCARRIER = "Sonstige"
KNOWN_SECTORS = ("Strom", "Wärme")  # alles andere -> "Sonstige"
SECTORS = ["Strom", "Wärme", "Sonstige"]


def split_carrier_subcarrier(raw, sep: str = CARRIER_SEP, default_sub: str = DEFAULT_SUBCARRIER) -> tuple[str, str]:
    """
    Zerlegt einen Carrier-String im Format 'Carrier_Subcarrier' in (Carrier, Subcarrier). 
    Falls kein Subcarrier vorhanden ist, wird ein Default-Subcarrier (Sonstige) gesetzt.
    
    Inputs: Inhalt des Carrier-Attributs
    
    Output: Carrier, Subcarrier
    raw = "Carrier_Subcarrier" -> ("Carrier","Subcarrier")
    raw = "Carrier"            -> ("Carrier", default_sub)
    raw = NaN/None             -> ("", default_sub)
    """
    if raw is None or pd.isna(raw):
        return ("", default_sub)
    s = str(raw).strip()
    if not s:
        return ("", default_sub)
    if sep in s:
        a, b = s.split(sep, 1)  # nur am ersten Separator splitten
        a = a.strip()
        b = b.strip()
        return (a if a else "", b if b else default_sub)
    return (s, default_sub)


def sector_subcarrier_from_raw_carrier(raw_carrier) -> tuple[str, str]:
    """
   Leitet aus einem raw carrier den Sektor (nur bekannte Sektoren) und den Subcarrier ab.
       
   Inputs: raw_carrier: Carrier-Feld (z.B. aus n.buses['carrier'] oder r['carrier']).
       
   Ruft split_carrier_subcarrier auf.
   Setzt sector = carrier, wenn carrier in KNOWN_SECTORS, sonst 'Sonstige'.
   Stellt sicher, dass subcarrier nicht leer ist (Default).
       
   Outputs: Tuple[str, str]: (sector, subcarrier)
    """
    carrier, sub = split_carrier_subcarrier(raw_carrier)
    sector = carrier if carrier in KNOWN_SECTORS else "Sonstige"
    if not sub:
        sub = DEFAULT_SUBCARRIER
    return sector, sub


def ensure_bus_taxonomy(n: pypsa.Network) -> None:
    """
    Erzeugt/aktualisiert die Spalten n.buses['sector'] und n.buses['subcarrier'] aus
    n.buses['carrier'].
    
    Inputs: n.pypsa.Network
    
    Abbruch, wenn n.buses fehlt/ leer ist
    Stellt sicher, dass Spalte "carrier" existiert (sonst NA)
    Iteriert über alle Buses, mappt Carrier -> Sector, Subcarrier
    Schreibt die Series als String in n.buses
    
    Outputs: Keine (Inplace-Modifikation von n.buses)        
    """
    if not hasattr(n, "buses") or n.buses is None or n.buses.empty:
        return
    if "carrier" not in n.buses.columns:
        n.buses["carrier"] = pd.NA

    sec = []
    sub = []
    for v in n.buses["carrier"].tolist():
        s, sc = sector_subcarrier_from_raw_carrier(v)
        sec.append(s)
        sub.append(sc)

    n.buses["sector"] = pd.Series(sec, index=n.buses.index, dtype="string")
    n.buses["subcarrier"] = pd.Series(sub, index=n.buses.index, dtype="string")


def sector_subcarrier_from_bus(n: pypsa.Network, bus_name: str) -> tuple[str, str]:
    """
    Gibt (sector, subcarrier) für einen spezifischen Busnamen zurück, bevorzugt aus
    n.buses['sector'/'subcarrier'], sonst aus n.buses['carrier'].
    
    Inputs: n.pypsa.Network, bus_name
    
    Validiert bus_name und Existenz in n.buses.
    Wenn 'sector' und 'subcarrier' existieren: liest Werte robust (NA -> Default).
    Sonst: ruft sector_subcarrier_from_raw_carrier auf Basis von n.buses.at[bus_name,'carrier']
    auf.
    
    Outputs: Tuple[str, str]: (sector, subcarrier)
    """
    if not bus_name or bus_name not in n.buses.index:
        return ("Sonstige", DEFAULT_SUBCARRIER)
    if "sector" in n.buses.columns and "subcarrier" in n.buses.columns:
        s = n.buses.at[bus_name, "sector"]
        sc = n.buses.at[bus_name, "subcarrier"]
        s = "Sonstige" if pd.isna(s) else str(s)
        sc = DEFAULT_SUBCARRIER if pd.isna(sc) else str(sc)
        return (s, sc)
    return sector_subcarrier_from_raw_carrier(n.buses.at[bus_name, "carrier"])

def sector_subcarrier_from_component_row(n: pypsa.Network, comp: str, r: pd.Series) -> tuple[str, str]:
    """
    Ermittelt (sector, subcarrier) für eine Komponentenzeile. Für Links/Lines erfolgt die
    Zuordnung über den Bus; sonst bevorzugt über 'carrier' der Komponente, mit Fallback auf
    den Bus.
    
    Inputs: n.pypsa.Network,
            comp (Komponentenname)
            r.pd.Series (Zeile der statischen Komponententabelle)
    
    Für Links/Lines: liest Bus aus r['bus'] und mappt per sector_subcarrier_from_bus.
    Sonst: versucht r['carrier'] zu interpretieren (sector_subcarrier_from_raw_carrier).
    Wenn daraus 'Sonstige' entsteht: Fallback auf r['bus'] (falls vorhanden) und übernimmt ggf.
    spezifischeren Subcarrier.
    
    Outputs: Tuple: [str, str]: (sector, subcarrier)
    """
    if comp in ("links", "lines"):
        b = r.get("bus", None)
        return sector_subcarrier_from_bus(n, b) if b is not None else ("Sonstige", DEFAULT_SUBCARRIER)

    raw_car = r.get("carrier", None)
    s, sc = sector_subcarrier_from_raw_carrier(raw_car)

    if s == "Sonstige":
        b = r.get("bus", None)
        if b is not None:
            s2, sc2 = sector_subcarrier_from_bus(n, b)
            s = s2
            if sc == DEFAULT_SUBCARRIER and sc2 != DEFAULT_SUBCARRIER:
                sc = sc2

    return (s, sc)



#%% Helper: Labels + Farbschemata


def strip_prefix(s: str) -> str:
    """
    Entfernt einen optionalen Komponenten-Prefix 'comp__' aus einem Label.
    
    Inputs: s[str]
    
    Trennt am ersten "__" und gibt den dahinterstehenden Teil des String zurück
    
    Outputs: Inplace-Modifikation, bereinigter String

    """
    s = str(s)
    return s.split("__", 1)[1] if "__" in s else s

# Anzeigenamen für Labels
_VAR_SUFFIX_RE = re.compile(r"(?i)_(variable|variabel|port)$")

def strip_variable_suffix(s: str) -> str:
    """
    Entfernt ein optionales Suffix '_variable' (case-insensitive) aus einem Label.
    
    Inputs: s [str]
    
    Regex-Substitution auf dem String
    
    Outputs: Inplace-Modifikation, bereinigter String

    """
    return _VAR_SUFFIX_RE.sub("", str(s))

_PORT_ONLY_SUFFIX_RE = re.compile(r"(?i)_(p|e)$")

def strip_port_suffix_for_hover(label: str) -> str:
    """
    Entfernt nur Endungen _p oder _e am Ende des Labels (für Hover).
    Beispiele:
      'Stromnetz_p'     -> 'Stromnetz'
      'Stromnetz_e'     -> 'Stromnetz'
      'Stromnetz_out1'  -> bleibt unverändert
      'Stromnetz_p (2)' -> 'Stromnetz (2)'
     
    Inputs: label [str]
    
    Separiert optionales Duplikatsuffix ' (n)'.
    entfernt anschließend per Regex nur Endungen '_p' oder '_e' im Kernstring.
    Setzt Duplikatsuffix wieder an.
    
    Outputs: Bereinigtes Hover-Label [str]        
    """
    s = str(label)

    m = re.match(r"^(.*?)(\s\(\d+\))$", s)
    if m:
        core, dup = m.group(1), m.group(2)
    else:
        core, dup = s, ""

    core = _PORT_ONLY_SUFFIX_RE.sub("", core)
    return core + dup

def display_name_map(names: list[str], show_component_on_dupes: bool = False) -> dict[str, str]:
    """
    Erzeugt eine Map raw_name -> Anzeige-Name und behandelt Duplikate (z.B. gleiche Namen
    aus verschiedenen Komponenten) deterministisch.
    
    Inputs: names: list[str] Rohspaltennamen/ Labels)
            component_on_dupes[bool]: wenn True, hängt bei Duplikaten den Komponententyp in
            eckigen Klammern an. (z. B. bei Stores mit separatem Bus relevant, Fallback für
                                  Differenzierbarkeit bei gleicher Benennung)
    
    Erzeugt 'pretty' Namen durch strip_prefix + strip_variable_suffix.
    Zählt Duplikate via Counter.
    Für eindeutige Namen: gibt pretty zurück.
    Für Duplikate: nummeriert '(1)', '(2)' oder hängt Komponententyp an (optional).
    
    Outputs: dict[str, str]: Mapping raw -> display.
    """
    pretties = [strip_variable_suffix(strip_prefix(n)) for n in names]
    cnt = Counter(pretties)

    out = {}
    seen = Counter()

    for raw, pretty in zip(names, pretties):
        if cnt[pretty] > 1:
            if show_component_on_dupes and "__" in str(raw):
                comp = str(raw).split("__", 1)[0]
                out[raw] = f"{pretty} [{comp}]"
            else:
                seen[pretty] += 1
                out[raw] = f"{pretty} ({seen[pretty]})"
        else:
            out[raw] = pretty

    return out

def _unique_preserve(seq):
    """
    Entfernt Duplikate aus einer Sequenz, behält aber die ursprüngliche Reihenfolge bei.
    
    Inputs: sep: Iterable
    
    Iteriert, merkt sich bereits gesehene Werte in einem set, baut eine Ausgabeliste.
    
    Outputs: List, eindeutige Elemente in Eingabereihenfolge

    """
    seen = set()
    out = []
    for x in seq:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _collect_subcarriers(*objs) -> list[str]:
    """
    Sammelt Subcarrier-Werte aus mehreren DataFrames und/oder dict[str->DataFrame] robust
    (None/leer wird ignoriert).
    
    Inputs: objs: beliebige Objekte (DataFrame oder dict)
    
    Iteriert über alle Objekte; extrahiert Spalte 'subcarrier', wenn vorhanden.
    Trimmt Whitespace, entfernt leere Strings.
    Bildet eindeutige Menge und sortiert.
    Platziert DEFAULT_SUBCARRIER ans Ende (falls vorhanden).
    
    Outputs: list[str]: Sortierte Subcarrier-Liste
    """
    vals = []
    for obj in objs:
        if obj is None:
            continue
        if isinstance(obj, dict):
            for _k, df in obj.items():
                if isinstance(df, pd.DataFrame) and (not df.empty) and ("subcarrier" in df.columns):
                    vals.extend(df["subcarrier"].dropna().astype(str).tolist())
        elif isinstance(obj, pd.DataFrame):
            if (not obj.empty) and ("subcarrier" in obj.columns):
                vals.extend(obj["subcarrier"].dropna().astype(str).tolist())
    vals = [v.strip() for v in vals if str(v).strip() != ""]
    uniq = sorted(set(vals))
    if DEFAULT_SUBCARRIER in uniq:
        uniq = [u for u in uniq if u != DEFAULT_SUBCARRIER] + [DEFAULT_SUBCARRIER]
    return uniq


def make_subcarrier_color_map(subcarriers: list[str]) -> dict[str, str]:
    """
    Erstellt eine deterministische Farbzuordnung subcarrier -> Farbe anhand mehrerer
    Plotly-Paletten.
    
    Inputs: subcarriers: list[str]
    
    Kombiniert mehrere qualitative Paletten, entfernt Duplikate.
    Bei Bedarf Palette zyklisch verlängern.
    Zuweisung in der Reihenfolge der Eingabeliste.
    
    Outputs: dict[str;str]: subcarrier => Farbcode
    """
    palettes = (
        px.colors.qualitative.Safe
        + px.colors.qualitative.Bold
        + px.colors.qualitative.Dark24
        + px.colors.qualitative.Alphabet
    )
    colors = _unique_preserve(palettes)

    if not subcarriers:
        return {}

    if len(subcarriers) > len(colors):
        rep = int(math.ceil(len(subcarriers) / len(colors)))
        colors = (colors * rep)[:len(subcarriers)]
    else:
        colors = colors[:len(subcarriers)]

    out = {}
    fallback_iter = iter(colors)
    for sc in subcarriers:
        out[sc] = _semantic_color_for_label(sc)
        if out[sc] is None:
            out[sc] = next(fallback_iter, colors[len(out) % len(colors)])
    return out


def make_label_color_map(labels: list[str]) -> dict[str, str]:
    """
    Erstellt eine deterministische Farbzuordnung für beliebige Labels (z.B. Zeitreihen-Spalten).
    
    Inputs: labels: list[str]

    Kombiniert Paletten, erzeugt eindeutige Farbenliste.
    normalisiert/ trimmt Labels, bildet eindeutige sortierte Menge.
    Bei Bedarf Palette zyklisch verlängern.
    
    Outputs: dict[str,str]: label => Farbe
    """
    palettes = (
        px.colors.qualitative.Safe
        + px.colors.qualitative.Bold
        + px.colors.qualitative.Dark24
        + px.colors.qualitative.Alphabet
    )
    colors = _unique_preserve(palettes)

    labels = [str(l) for l in labels if str(l).strip() != ""]
    uniq = sorted(set(labels))
    if not uniq:
        return {}

    if len(uniq) > len(colors):
        rep = int(math.ceil(len(uniq) / len(colors)))
        colors = (colors * rep)[:len(uniq)]
    else:
        colors = colors[:len(uniq)]

    out = {}
    fallback_idx = 0
    for lab in uniq:
        col = _semantic_color_for_label(lab)
        if col is None:
            col = colors[fallback_idx % len(colors)]
            fallback_idx += 1
        out[lab] = col
    return out


def _semantic_color_for_label(label: str | None) -> str | None:
    """
    Ordnet bekannten Technologien, Kennzahlen und Kostenarten eine feste Farbe zu.
    
    Inputs: label.
    Outputs: Hex-Farbwert oder None, wenn kein Treffer vorliegt.
    """
    if label is None:
        return None
    text = str(label)
    text_norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    direct = SEMANTIC_COLORS.get(text)
    if direct:
        return direct
    checks = [
        ("pv-erzeugung", "PV-Erzeugung"),
        ("pv_erzeugung", "PV-Erzeugung"),
        ("pverzeugung", "PV-Erzeugung"),
        ("pv-eigenverbrauch", "PV-Eigenverbrauch"),
        ("pv_eigenverbrauch", "PV-Eigenverbrauch"),
        ("pveigenverbrauch", "PV-Eigenverbrauch"),
        ("pv-einspeisung", "PV-Einspeisung"),
        ("pv_einspeisung", "PV-Einspeisung"),
        ("pveinspeisung", "PV-Einspeisung"),
        ("strombezug", "Strombezug"),
        ("waerme_netzbezug", "Wärme_Netzbezug"),
        ("warme_netzbezug", "Wärme_Netzbezug"),
        ("waermespeicher", "Wärme_Speicher"),
        ("warme_speicher", "Wärme_Speicher"),
        ("warmespeicher", "Wärme_Speicher"),
        ("pv", "PV"),
        ("solarthermie", "Solarthermie"),
        ("bhkw", "BHKW"),
        ("waermepumpe", "Wärmepumpe"),
        ("warmepumpe", "Wärmepumpe"),
        ("gaskessel", "Gaskessel"),
        ("fernwaerme", "Fernwärme"),
        ("fernwarme", "Fernwärme"),
        ("gasnetz", "Gasnetzbezug"),
        ("stromnetz", "Stromnetz_Bezug"),
        ("netzbezug", "Netzbezug"),
        ("einspeis", "Einspeisung"),
        ("stromspeicher", "Stromspeicher"),
        ("gasspeicher", "Gasspeicher"),
        ("capex", "CAPEX"),
        ("opex", "OPEX"),
        ("co2", "CO2"),
        ("gesamtstromlast", "Strom"),
        ("netto-stromlast", "Strom"),
        ("reststromlast", "Strom"),
        ("stromlast", "Strom"),
        ("waermelast", "Wärme"),
        ("warmelast", "Wärme"),
        ("waerme", "Wärme"),
        ("warme", "Wärme"),
        ("gas", "Gas"),
        ("strom", "Strom"),
    ]
    for needle, key in checks:
        if needle in text_norm:
            return SEMANTIC_COLORS.get(key)
    return None


def make_cost_color_map() -> dict[str, str]:
    """
    Definiert ein konsistentes Farbschema für Kostenarten.
    
    Inputs: Keine
    
    Nimmt Farben der Plotly-Vivid-Palette (mit Fallback-Hexcodes).
    
    Outputs: dict[str,str]: Mapping Kostenarten => Farben

    """
    return {
        "CAPEX": SEMANTIC_COLORS["CAPEX"],
        "OPEX": SEMANTIC_COLORS["OPEX"],
        "CO2": SEMANTIC_COLORS["CO2"],
        "Cashflow": SEMANTIC_COLORS["OPEX"],
        "Kumuliert": SEMANTIC_COLORS["Kumuliert"],
        "Vorteil": SEMANTIC_COLORS["Vorteil"],
        "Nachteil": SEMANTIC_COLORS["Nachteil"],
    }

COST_COLOR_MAP = make_cost_color_map()


def empty_info_figure(title: str, message: str | None = None) -> go.Figure:
    """
    Erzeugt eine Hinweis-Abbildung, wenn für ein Diagramm keine Daten vorliegen.
    
    Inputs: title, message.
    Outputs: Plotly-Figure mit Hinweistext, ohne Achseninhalt.
    """
    message = message or "Für die aktuelle Auswahl liegen keine darstellbaren Daten vor."
    fig = go.Figure()
    fig.update_layout(
        title=title,
        meta={"empty_info": True, "empty_message": message},
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=150,
        margin=dict(l=20, r=20, t=50, b=20),
        annotations=[
            dict(
                text=message,
                x=0.5,
                y=0.45,
                xref="paper",
                yref="paper",
                showarrow=False,
                align="center",
                font=dict(family=BODY_FONT_FAMILY, size=16, color="#536471"),
            )
        ],
    )
    return fig


def _figure_title_text(fig: go.Figure | None) -> str:
    """
    Liest den Titel einer Plotly-Abbildung robust als Text aus.
    
    Inputs: fig.
    Outputs: Titeltext oder leerer String.
    """
    if fig is None or getattr(fig, "layout", None) is None or fig.layout.title is None:
        return ""
    return str(fig.layout.title.text or "")


def _empty_message_from_title(title: str) -> str | None:
    """
    Leitet aus bekannten Diagrammtiteln eine verständliche Hinweisnachricht ab.
    
    Inputs: title.
    Outputs: Hinweistext oder None.
    """
    title_lower = title.lower()
    if "keine datenbasis" in title_lower:
        return "Bitte zuerst eine Datenbasis auswählen."
    if "keine daten" in title_lower or "keine werte gefunden" in title_lower:
        return "Für die aktuelle Auswahl liegen keine darstellbaren Daten vor."
    if "nur bei mip" in title_lower:
        return "Dieses Diagramm ist nur für Multi-Investment-Perioden verfügbar."
    if "keine positiven kosten" in title_lower:
        return "Für die aktuelle Auswahl liegen keine positiven Kostenwerte vor."
    if "keine emissionsdifferenz" in title_lower:
        return "Zwischen den Varianten liegt keine Emissionsdifferenz vor."
    if "vergleich emittiert mehr co2" in title_lower:
        return "Die Vergleichsvariante emittiert mehr CO2 als die Datenbasis. Es entstehen daher keine CO2-Vermeidungskosten."
    return None


def is_empty_info_figure(fig: go.Figure | None) -> bool:
    """
    Erkennt, ob eine Plotly-Abbildung als reine Hinweis-Abbildung erzeugt wurde.
    
    Inputs: fig.
    Outputs: True, wenn es sich um eine Hinweis-Abbildung handelt.
    """
    if fig is None or getattr(fig, "layout", None) is None:
        return False
    meta = fig.layout.meta
    return isinstance(meta, dict) and bool(meta.get("empty_info"))


def finalize_figure(fig: go.Figure | None) -> go.Figure:
    """
    Wendet das gemeinsame Diagrammlayout auf eine einzelne Plotly-Abbildung an.
    
    Inputs: fig.
    Outputs: formatierte Plotly-Abbildung oder Hinweis-Abbildung.
    """
    if fig is None:
        return empty_info_figure("Keine Daten")
    title = _figure_title_text(fig)
    empty_message = _empty_message_from_title(title)
    if empty_message and not is_empty_info_figure(fig):
        clean_title = re.sub(r"\s*\([^)]*keine[^)]*\)", "", title, flags=re.IGNORECASE).strip() or "Hinweis"
        return empty_info_figure(clean_title, empty_message)
    if len(fig.data) == 0 and not is_empty_info_figure(fig):
        return empty_info_figure(
            title or "Keine darstellbaren Daten",
            "Für diese Auswahl liegen keine darstellbaren Werte vor.",
        )

    fig.update_layout(
        font=dict(family=BODY_FONT_FAMILY, size=BASE_FONT_SIZE_PX, color="#1f3555"),
        title=dict(font=dict(family=HEADING_FONT_FAMILY, size=TITLE_FONT_SIZE_PX, color="#0f3554")),
        separators=",.",
        autosize=True,
        uniformtext=dict(minsize=12, mode="hide"),
    )

    margin = fig.layout.margin.to_plotly_json() if fig.layout.margin else {}
    fig.update_layout(
        margin=dict(
            l=max(int(margin.get("l") or 0), 78),
            r=max(int(margin.get("r") or 0), 78),
            t=max(int(margin.get("t") or 0), 78),
            b=max(int(margin.get("b") or 0), 70),
        )
    )
    axis_updates = dict(
        automargin=True,
        title_standoff=14,
        tickfont=dict(size=14),
    )
    fig.update_xaxes(**axis_updates)
    fig.update_yaxes(**axis_updates)
    if getattr(fig.layout, "yaxis2", None):
        fig.update_layout(yaxis2=dict(automargin=True, title_standoff=14, tickfont=dict(size=14)))
    return fig


def finalize_figures(*figs: go.Figure) -> tuple[go.Figure, ...]:
    """
    Wendet das gemeinsame Diagrammlayout auf mehrere Plotly-Abbildungen an.
    
    Inputs: *figs.
    Outputs: Tupel formatierter Plotly-Abbildungen.
    """
    return tuple(finalize_figure(fig) for fig in figs)


def format_number_de(value, digits: int = 2) -> str:
    """
    Formatiert Zahlen mit deutscher Dezimalschreibweise für Mouseover-Texte und Tabellen.
    
    Inputs: value, digits.
    Outputs: formatierter Zahlenstring oder "-".
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if not np.isfinite(number):
        return "-"
    return f"{number:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def period_filter_note(text: str | None = None) -> html.Div:
    """
    Erzeugt einen einheitlichen Hinweistext zur Wirkung des Periodenfilters.
    
    Inputs: text.
    Outputs: Dash-HTML-Container mit Hinweistext.
    """
    return html.Div(
        text or "Hinweis: Einige Diagramme bilden bewusst alle Investitionsperioden ab. Der Periodenfilter wirkt daher nicht auf jede Darstellung.",
        className="dashboard-note",
    )


def register_agenda(items: list[tuple[str, str]], title: str = "Inhalte dieser Registerkarte") -> html.Div | None:
    """
    Erstellt eine kompakte Übersicht am Anfang für umfangreiche Registerkarten.

    Inputs: Liste aus (Anker-ID, sichtbarer Überschrift) und optionaler Titel.
    Outputs: Dash-HTML-Container mit internen Links oder None bei zu wenigen Einträgen.
    """
    clean_items = [
        (str(anchor).strip(), str(label).strip())
        for anchor, label in (items or [])
        if str(anchor).strip() and str(label).strip()
    ]
    if len(clean_items) <= 3:
        return None

    return html.Div(
        className="register-agenda",
        children=[
            html.Div(title, className="register-agenda-title"),
            html.Ul(
                className="register-agenda-list",
                children=[
                    html.Li(
                        html.A(label, href=f"#{anchor}", className="register-agenda-link")
                    )
                    for anchor, label in clean_items
                ],
            ),
        ],
    )


def diagram_anchor(anchor_id: str, title: str, level: int = 3):
    """
    Erzeugt eine Diagrammüberschrift mit internem Anker für dei Registerkartenübersicht.

    Inputs: Anker-ID, Überschrift und gewünschte Überschriftenebene.
    Outputs: html.H3/html.H4 mit CSS-Scrollabstand.
    """
    heading_cls = "diagram-anchor"
    if level == 4:
        return html.H4(title, id=anchor_id, className=heading_cls)
    return html.H3(title, id=anchor_id, className=heading_cls)


def scroll_anchor(anchor_id: str) -> html.Div:
    """
    Setzt einen unsichtbaren Sprungpunkt vor Diagrammen ohne eigene Abschnittsüberschrift.

    Inputs: Anker-ID.
    Outputs: leerer Dash-Container als Scroll-Ziel.
    """
    return html.Div(id=anchor_id, className="scroll-anchor")


#%% Helper: Interaktive Systemkarte

# Verdichtung der PyPSA-Komponenten mit gültigen Koordinaten und relevanter Leistung zu Leaflet-Markern mit technischer Gruppierung und Mouseover-Informationen.
MAP_CRS_EPSG = "EPSG:4326"
MAP_CRS_NAME = "WGS 84"
MAP_AXIS_ORDER = "x=longitude, y=latitude"
MAP_DEFAULT_SOURCE = "PyPSA-Geometadaten"

MAP_LAYER_DEFS = [
    ("generators", "Generatoren", "Generator", "#3a9d5d", 13),
    ("loads", "Lasten", "Last", "#c74b3a", 13),
    ("storage_units", "Speicher", "Speicher", "#7a4fb3", 13),
    ("stores", "Stores", "Store", "#8a6f3d", 13),
    ("links", "Sonstige Links", "Link", "#e08d2d", 11),
    ("lines", "Leitungen", "Leitung", "#707070", 11),
    ("transformers", "Transformatoren", "Transformator", "#4f8c8c", 11),
]
MAP_LAYER_BY_KEY = {
    key: {"label": label, "singular": singular, "color": color, "size": size}
    for key, label, singular, color, size in MAP_LAYER_DEFS
}
MAP_TECH_LAYER_DEFS = {
    "generators:Netzanschlusspunkt": ("Netzanschlusspunkt", "Netzanschlusspunkt", "#2f6f9f", 13),
    "generators:Fernwärmebezug": ("Fernwärmebezug", "Fernwärmebezug", "#2a9d8f", 13),
    "generators:Gasnetzbezug": ("Gasnetzbezug", "Gasnetzbezug", "#8a6f3d", 13),
    "generators:PV": ("PV", "PV-Anlage", "#f0b429", 13),
    "generators:Solarthermie": ("Solarthermie", "Solarthermieanlage", "#e08d2d", 13),
    "loads:Stromlast": ("Stromlast", "Stromlast", "#2f6f9f", 13),
    "loads:Wärmelast": ("Wärmelast", "Wärmelast", "#c74b3a", 13),
    "links:BHKW": ("BHKW", "BHKW", "#5b6bb8", 12),
    "links:Wärmepumpe": ("Wärmepumpe", "Wärmepumpe", "#4bb6a5", 12),
    "links:Gaskessel": ("Gaskessel", "Gaskessel", "#8a6f3d", 12),
    "storage:Stromspeicher": ("Stromspeicher", "Stromspeicher", "#7a4fb3", 12),
    "storage:Wärmespeicher": ("Wärmespeicher", "Wärmespeicher", "#c45a9d", 12),
    "storage:Gasspeicher": ("Gasspeicher", "Gasspeicher", "#6d8f38", 12),
}
MAP_LAYER_ORDER = {
    "generators:Netzanschlusspunkt": 10,
    "generators:PV": 11,
    "generators:Solarthermie": 12,
    "generators:Fernwärmebezug": 13,
    "generators:Gasnetzbezug": 14,
    "generators": 19,
    "loads": 20,
    "loads:Stromlast": 21,
    "loads:Wärmelast": 22,
    "links:BHKW": 30,
    "links:Wärmepumpe": 31,
    "links:Gaskessel": 32,
    "storage:Stromspeicher": 33,
    "storage:Wärmespeicher": 34,
    "storage:Gasspeicher": 35,
    "links": 39,
    "storage_units": 40,
    "stores": 41,
    "lines": 50,
    "transformers": 51,
}
MAP_LAYER_SYMBOLS = {
    "generators:Netzanschlusspunkt": "NA",
    "generators:PV": "PV",
    "generators:Solarthermie": "ST",
    "generators:Fernwärmebezug": "FW",
    "generators:Gasnetzbezug": "GN",
    "loads:Stromlast": "SL",
    "loads:Wärmelast": "WL",
    "links:BHKW": "BHKW",
    "links:Wärmepumpe": "WP",
    "links:Gaskessel": "GK",
    "storage:Stromspeicher": "ES",
    "storage:Wärmespeicher": "WS",
    "storage:Gasspeicher": "GS",
}
MAP_ICON_ASSET_DIR = "map-icons"
MAP_LAYER_ICON_FILES = {
    "generators:Netzanschlusspunkt": "netzanschlusspunkt.png",
    "generators:PV": "pv.png",
    "generators:Solarthermie": "solarthermie.png",
    "generators:Fernwärmebezug": "fernwaermebezug.png",
    "generators:Gasnetzbezug": "gasnetzbezug.png",
    "loads:Stromlast": "stromlast.png",
    "loads:Wärmelast": "waermelast.png",
    "links:BHKW": "bhkw.png",
    "links:Wärmepumpe": "waermepumpe.png",
    "links:Gaskessel": "gaskessel.png",
    "storage:Stromspeicher": "stromspeicher.png",
    "storage:Wärmespeicher": "waermespeicher.png",
    "storage:Gasspeicher": "gasspeicher.png",
}
MAP_ICON_SIZE_PX = 45
MAP_DEFAULT_LAYERS = ["generators", "loads", "storage_units", "links", "lines"]
MAP_FIGURE_HEIGHT = 1248
MAP_EXISTENCE_EPS = 1e-9
MAP_STATIC_EXISTENCE_COLUMNS = (
    "p_nom_opt",
    "p_nom",
    "s_nom_opt",
    "s_nom",
    "e_nom_opt",
    "e_nom",
    "p_set",
    "q_set",
)
MAP_DYNAMIC_EXISTENCE_ATTRS = (
    "p",
    "p0",
    "p1",
    "p2",
    "p_set",
    "q",
    "q_set",
    "s",
    "e",
    "state_of_charge",
)


def _map_float(value):
    """
    Hilfsfunktion für die Systemkarte: bereitet map float auf.
    
    Inputs: value.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    try:
        if value is None or pd.isna(value):
            return None
        val = float(value)
    except Exception:
        return None
    if not np.isfinite(val):
        return None
    return val


def _valid_lon_lat(lon, lat) -> bool:
    """
    Prüft, ob die Werte für Längen- und Breitengrad als gültige Kartenkoordinate verwendet werden können.
    
    Inputs: lon, lat.
    Outputs: Koordinate ist True oder False.
    """
    lon_f = _map_float(lon)
    lat_f = _map_float(lat)
    if lon_f is None or lat_f is None:
        return False
    if abs(lon_f) < 1e-12 and abs(lat_f) < 1e-12:
        return False
    if abs(lon_f) > 25.0 and 45.0 <= lon_f <= 56.0 and 5.0 <= lat_f <= 16.0:
        return False
    return -180.0 <= lon_f <= 180.0 and -90.0 <= lat_f <= 90.0


def _text_or_default(value, default: str = "") -> str:
    """
    Erzeugt aus einem Wert einen sauberen Text, um Fehlerhafteausgaben zu verhindern.
    
    Inputs: value, default.
    Outputs: Sauberer Textstring.
    """
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    text = str(value).strip()
    return text if text else default


def _row_lon_lat(row: pd.Series) -> tuple[float | None, float | None]:
    """
    Holt aus einer Tabellenzeile die Kartenkoordinaten.
    
    Inputs: row.
    Outputs: Gültige Koordinaten.
    """
    if "x" not in row.index or "y" not in row.index:
        return None, None
    lon = _map_float(row.get("x"))
    lat = _map_float(row.get("y"))
    if _valid_lon_lat(lon, lat):
        return lon, lat
    return None, None


def _component_bus_names(component: str, row: pd.Series) -> list[str]:
    """
    Sammelt Busse, an denen eine PyPSA-Komponente angeschlossen ist.
    
    Inputs: component, row.
    Outputs: Liste mit Busnamen, an denen die Komponente angeschlossen ist.
    """
    buses = []
    if component in ("generators", "loads", "storage_units", "stores"):
        b = row.get("bus", None)
        if b is not None and not pd.isna(b) and str(b).strip():
            buses.append(str(b))
        return buses

    for i in range(0, 10):
        col = f"bus{i}"
        if col not in row.index:
            continue
        b = row.get(col, None)
        if b is not None and not pd.isna(b) and str(b).strip():
            buses.append(str(b))
    return _unique_preserve(buses)


def _map_component_sector(n: pypsa.Network, component: str, row: pd.Series) -> tuple[str, str]:
    """
    Entscheidet welchem Sektor und Subcarrier eine Komponente angehört.
    
    Inputs: n, component, row.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    if component in ("generators", "loads", "storage_units", "stores"):
        return sector_subcarrier_from_component_row(n, component, row)
    if component in ("links", "lines", "transformers"):
        for b in _component_bus_names(component, row):
            if b in n.buses.index:
                return sector_subcarrier_from_bus(n, b)
    return ("Sonstige", DEFAULT_SUBCARRIER)


def _map_technology_layer(component: str, name: str, row: pd.Series) -> tuple[str, str, str, str, int]:
    """
    Bereitet map technology layer, wie Technologiegruppe oder Kartenebene für die Komponenten auf.
    
    Inputs: component, name, row.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    component = str(component)
    name_text = str(name)
    carrier_text = _text_or_default(row.get("carrier"), "")
    map_label_text = _text_or_default(row.get("map_label"), "")
    text = f"{name_text} {carrier_text} {map_label_text}"

    tech_key = None
    if component == "generators":
        if re.search(r"Stromnetz[_-]?Bezug|Einspeis", text, flags=re.IGNORECASE):
            tech_key = "generators:Netzanschlusspunkt"
        elif re.search(r"Fernw(?:ä|ae)rme[_-]?Bezug", text, flags=re.IGNORECASE):
            tech_key = "generators:Fernwärmebezug"
        elif re.search(r"Gasnetz[_-]?Bezug", text, flags=re.IGNORECASE):
            tech_key = "generators:Gasnetzbezug"
        elif re.search(r"(^|[_\s-])PV([_\s-]|\d|$)", text, flags=re.IGNORECASE):
            tech_key = "generators:PV"
        elif re.search(r"Solarthermie", text, flags=re.IGNORECASE):
            tech_key = "generators:Solarthermie"
    elif component == "loads":
        if re.search(r"Stromlast", text, flags=re.IGNORECASE):
            tech_key = "loads:Stromlast"
        elif re.search(r"W(?:ä|ae)rmelast", text, flags=re.IGNORECASE):
            tech_key = "loads:Wärmelast"
    elif component == "links":
        if re.search(r"BHKW", text, flags=re.IGNORECASE):
            tech_key = "links:BHKW"
        elif re.search(r"W(?:ä|ae)rmepumpe", text, flags=re.IGNORECASE):
            tech_key = "links:Wärmepumpe"
        elif re.search(r"Gaskessel", text, flags=re.IGNORECASE):
            tech_key = "links:Gaskessel"
        elif re.search(r"Stromspeicher", text, flags=re.IGNORECASE):
            tech_key = "storage:Stromspeicher"
        elif re.search(r"W(?:ä|ae)rmespeicher", text, flags=re.IGNORECASE):
            tech_key = "storage:Wärmespeicher"
        elif re.search(r"Gasspeicher", text, flags=re.IGNORECASE):
            tech_key = "storage:Gasspeicher"
    elif component in ("storage_units", "stores"):
        if re.search(r"Stromspeicher", text, flags=re.IGNORECASE):
            tech_key = "storage:Stromspeicher"
        elif re.search(r"W(?:ä|ae)rmespeicher", text, flags=re.IGNORECASE):
            tech_key = "storage:Wärmespeicher"
        elif re.search(r"Gasspeicher", text, flags=re.IGNORECASE):
            tech_key = "storage:Gasspeicher"

    if tech_key and tech_key in MAP_TECH_LAYER_DEFS:
        label, singular, color, size = MAP_TECH_LAYER_DEFS[tech_key]
        return tech_key, label, singular, color, size

    layer = MAP_LAYER_BY_KEY.get(
        component,
        {"label": component, "singular": "Komponente", "color": "#666", "size": 11},
    )
    return component, layer["label"], layer["singular"], layer["color"], layer["size"]


def _map_layer_symbol(layer_key: str, layer_label: str = "") -> str:
    """
    Bereitet map layer symbol auf.
    
    Inputs: layer_key, layer_label.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    symbol = MAP_LAYER_SYMBOLS.get(str(layer_key), "")
    if symbol:
        return symbol
    label = _text_or_default(layer_label, "")
    if label:
        return label[:2].upper()
    return "•"


def _map_icon_asset_url(layer_key: str) -> str:
    """
    Sucht für eine Kartenebene das passende Icon-Bild.
    
    Inputs: layer_key.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    filename = MAP_LAYER_ICON_FILES.get(str(layer_key), "")
    if not filename:
        return ""
    icon_path = os.path.join(BASE_DIR, "assets", MAP_ICON_ASSET_DIR, filename)
    if not os.path.exists(icon_path):
        return ""
    return f"/assets/{MAP_ICON_ASSET_DIR}/{filename}"


def _map_html_text(value) -> str:
    """
   Bereitet die Texte auf, so das sie in einem HTML-Popup auf der Karte angezeigt werden können.
    
    Inputs: value.
    Outputs: HTML-String oder HTML-Layoutbaustein.
    """
    text = _text_or_default(value, "")
    return html_escape(text).replace("&lt;br&gt;", "<br>")


def _map_popup_html(row: pd.Series) -> str:
    """
    Aufbau des Textes für das Popup auf der Systemkarte.
    
    Inputs: row.
    Outputs: HTML-String oder HTML-Layoutbaustein.
    """
    display_name = _map_html_text(row.get("display_name"))
    lon_text = format_number_de(row.get("lon"), 6)
    lat_text = format_number_de(row.get("lat"), 6)
    accuracy_value = _map_float(row.get("accuracy_m"))
    accuracy_text = format_number_de(accuracy_value, 1) if accuracy_value is not None else (_map_html_text(row.get("accuracy_m")) or "nicht angegeben")
    parts = [
        f"<b>{display_name}</b>",
        f"Ebene: {_map_html_text(row.get('layer_label'))}",
        f"Komponenten: {_map_html_text(row.get('component_count'))}",
        f"Sektor: {_map_html_text(row.get('sector'))} / {_map_html_text(row.get('subcarrier'))}",
        f"Bus: {_map_html_text(row.get('bus_summary')) or 'kein Busbezug'}",
        f"Kapazität: {_map_html_text(row.get('capacity')) or 'nicht angegeben'}",
        f"Details:<br>{_map_html_text(row.get('component_details'))}",
        f"Koordinate: {lon_text}, {lat_text}",
        f"CRS: {_map_html_text(row.get('crs'))}",
        f"Koordinaten-Epoche: {_map_html_text(row.get('coordinate_epoch'))}",
        f"Quelle: {_map_html_text(row.get('source'))}",
        f"Lagegenauigkeit: {accuracy_text} m",
    ]
    return "<br>".join(parts)


def _map_layer_order_value(layer_key: str, component: str | None = None) -> int:
    """
    Sortiert die Kartenebenen.
    
    Inputs: layer_key, component.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    if layer_key in MAP_LAYER_ORDER:
        return MAP_LAYER_ORDER[layer_key]
    if component in MAP_LAYER_ORDER:
        return MAP_LAYER_ORDER[str(component)]
    return 99


def _map_capacity_text(component: str, row: pd.Series) -> str:
    """
    Bereitet die Kapazitätstexte auf der Karte auf.
    
    Inputs: component, row.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    candidates = [
        ("p_nom_opt", "kW"),
        ("p_nom", "kW"),
        ("s_nom_opt", "kW"),
        ("s_nom", "kW"),
        ("e_nom_opt", "kWh"),
        ("e_nom", "kWh"),
        ("max_hours", "h"),
    ]
    for col, unit in candidates:
        if col not in row.index:
            continue
        val = _map_float(row.get(col))
        if val is None:
            continue
        if abs(val) <= 1e-12 and col.endswith("_opt"):
            continue
        return f"{val:,.2f} {unit}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ""


def _map_static_has_nonzero_quantity(row: pd.Series) -> bool:
    """
    Prüft ob eine Komponente einen Leistungs- oder Kapazitätswert größer als 0 hat.
    
    Inputs: row.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    for col in MAP_STATIC_EXISTENCE_COLUMNS:
        if col not in row.index:
            continue
        val = _map_float(row.get(col))
        if val is not None and abs(val) > MAP_EXISTENCE_EPS:
            return True
    return False


def _map_dynamic_table(n: pypsa.Network, component: str, attr: str):
    """
    Bereitet die Tabellen aus PyPSA auf.
    
    Inputs: n, component, attr.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    if hasattr(n, "components") and hasattr(n.components, component):
        dyn = getattr(getattr(n.components, component), "dynamic", None)
        if dyn is not None:
            try:
                table = dyn.get(attr)
            except AttributeError:
                try:
                    table = dyn[attr]
                except Exception:
                    table = None
            if table is not None:
                return table

    legacy = getattr(n, f"{component}_t", None)
    if legacy is not None:
        return getattr(legacy, attr, None)
    return None


def _map_component_has_activity(n: pypsa.Network, component: str, name: str) -> bool:
    """
    Prüft ob eine Komponente auch aktiv ist.
    
    Inputs: n, component, name.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    for attr in MAP_DYNAMIC_EXISTENCE_ATTRS:
        table = _map_dynamic_table(n, component, attr)
        if table is None or not hasattr(table, "columns") or name not in table.columns:
            continue
        values = pd.to_numeric(table[name], errors="coerce").fillna(0.0)
        if not values.empty and float(values.abs().max()) > MAP_EXISTENCE_EPS:
            return True
    return False


def _map_component_exists(n: pypsa.Network, component: str, name: str, row: pd.Series) -> bool:
    """
    Überprüft die Komponenten auf Leistung, Kapazität und Aktivität.
    
    Inputs: n, component, name, row.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    if _map_static_has_nonzero_quantity(row):
        return True
    return _map_component_has_activity(n, component, name)


def filter_map_existing_components(n: pypsa.Network, df_map: pd.DataFrame) -> pd.DataFrame:
    """
    Entfernt Kartenkomponenten ohne reale Leistung, Kapazität oder Aktivität.
    
    Inputs: n, df_map.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    if n is None or df_map is None or df_map.empty:
        return pd.DataFrame()
    if not {"component", "name", "component_id"}.issubset(df_map.columns):
        return df_map.copy()

    existing_ids = set()
    for component, group in df_map.groupby(df_map["component"].astype(str), sort=False):
        table = getattr(n, component, None)
        if table is None or table.empty:
            continue
        for _, map_row in group.iterrows():
            name = str(map_row.get("name", ""))
            if name not in table.index:
                continue
            if _map_component_exists(n, component, name, table.loc[name]):
                existing_ids.add(str(map_row.get("component_id", "")))

    keep_mask = df_map["component_id"].astype(str).isin(existing_ids)
    return df_map.loc[keep_mask].copy()


def _map_base_display_name(name: str) -> str:
    """
    Wandelt technische Komponentennamen zu Anzeigenamen.
    
    Inputs: name.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    return strip_variable_suffix(strip_prefix(str(name)))


def _join_unique_text(values, fallback: str = "") -> str:
    """
    Verbindet Textpassagen miteinander, entfernt Duplikate und verbindet sie mit Kommata.
    
    Inputs: values, fallback.
    Outputs: Textstring mit eindeutigen Einträgen, getrennt durch Kommata.
    """
    items = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            source_values = value
        else:
            source_values = [value]
        for item in source_values:
            text = _text_or_default(item, "")
            if text and text not in items:
                items.append(text)
    return ", ".join(items) if items else fallback


def _map_detail_line(row: pd.Series) -> str:
    """
    Baut eine Detailzeile für eine Kartenkomponente.
    
    Inputs: row.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    name = _text_or_default(row.get("display_name"), _text_or_default(row.get("name"), "Komponente"))
    build_year = _text_or_default(row.get("build_year"), "")
    capacity = _text_or_default(row.get("capacity"), "")
    buses = _text_or_default(row.get("bus_summary"), "")

    parts = [name]
    if build_year:
        parts.append(f"Baujahr / Periode: {build_year}")
    if capacity:
        parts.append(f"Kapazität: {capacity}")
    if buses:
        parts.append(f"Bus: {buses}")
    return " | ".join(parts)


def _map_sort_group_for_hover(group: pd.DataFrame) -> pd.DataFrame:
    """
    Sortiert die Gruppen der Kartenkomponenten.
    
    Inputs: group.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    out = group.copy()
    out["_sort_year"] = pd.to_numeric(out.get("build_year", pd.Series(index=out.index)), errors="coerce")
    out["_sort_year"] = out["_sort_year"].fillna(999999).astype(int)
    out["_sort_name"] = out.get("display_name", out.get("name", pd.Series(index=out.index))).astype(str)
    return out.sort_values(["_sort_year", "_sort_name", "name"]).drop(columns=["_sort_year", "_sort_name"])


def _map_group_display_name(group: pd.DataFrame) -> str:
    """
    Bestimmt gemeinsamen Anzeigenamen für eine Gruppe von Kartenkomponenten.
    
    Inputs: group.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    base_names = [
        _text_or_default(v, "")
        for v in group.get("base_display_name", pd.Series(index=group.index)).tolist()
    ]
    base_names = [v for v in _unique_preserve(base_names) if v]
    if len(base_names) == 1:
        return base_names[0]
    return _text_or_default(group.iloc[0].get("layer_label"), "Komponenten")


def _map_group_capacity_summary(group: pd.DataFrame) -> str:
    """
    Baut die Kapazitäts-Zusammenfassung für einen zusammengefassten Kartenmarker auf.
    
    Inputs: group.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    group = _map_sort_group_for_hover(group)
    if len(group) == 1:
        return _text_or_default(group.iloc[0].get("capacity"), "")

    capacities = []
    year_counts = group["build_year"].astype(str).replace("", "ohne Periode").value_counts().to_dict()
    base_names = [
        _text_or_default(v, "")
        for v in group.get("base_display_name", pd.Series(index=group.index)).tolist()
    ]
    same_base = len([v for v in _unique_preserve(base_names) if v]) == 1

    for _, row in group.iterrows():
        capacity = _text_or_default(row.get("capacity"), "")
        if not capacity:
            continue
        year = _text_or_default(row.get("build_year"), "")
        label = _text_or_default(row.get("display_name"), _text_or_default(row.get("name"), "Komponente"))
        if year and same_base and year_counts.get(str(year), 0) == 1:
            capacities.append(f"{year}: {capacity}")
        else:
            capacities.append(f"{label}: {capacity}")

    capacities = _unique_preserve(capacities)
    if not capacities:
        return ""
    return "Zubau je Periode:<br>" + "<br>".join(capacities)


def _map_group_cols_for_overlapping_components(df_map: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Schaut welche Komponenten den gleichen Namen und Position haben.
    
    Inputs: df_map.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    out = df_map.copy()
    out["_group_lon"] = pd.to_numeric(out["lon"], errors="coerce").round(7)
    out["_group_lat"] = pd.to_numeric(out["lat"], errors="coerce").round(7)
    out["_group_base"] = out.get("base_display_name", out.get("display_name", "")).astype(str).str.strip()
    out.loc[out["_group_base"].eq(""), "_group_base"] = out.get("layer_label", "").astype(str)
    return out, ["map_layer_key", "layer_label", "_group_base", "_group_lon", "_group_lat"]


def aggregate_map_overlapping_components(df_map: pd.DataFrame) -> pd.DataFrame:
    """
    Fasst gleichartige Komponenten an identischer Koordinate zu einem Kartenmarker zusammen.
    
    Inputs: df_map.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    if df_map is None or df_map.empty:
        return pd.DataFrame()

    required_cols = ["map_layer_key", "layer_label", "base_display_name", "lon", "lat"]
    missing_cols = [col for col in required_cols if col not in df_map.columns]
    if missing_cols:
        return df_map.copy()

    df_group, group_cols = _map_group_cols_for_overlapping_components(df_map)
    missing_cols = [col for col in group_cols if col not in df_group.columns]
    if missing_cols:
        return df_map.copy()

    rows = []
    for _, group in df_group.groupby(group_cols, sort=False, dropna=False):
        group = _map_sort_group_for_hover(group)
        first = group.iloc[0].copy()
        first["component_id"] = "map_group|" + "|".join(group["component_id"].astype(str).tolist())
        first["component"] = _join_unique_text(group["component"].tolist(), fallback=str(first.get("component", "")))
        first["name"] = _join_unique_text(group["name"].tolist(), fallback=str(first.get("name", "")))
        first["base_name"] = _join_unique_text(group["base_name"].tolist(), fallback=str(first.get("base_name", "")))
        first["build_year"] = _join_unique_text(group["build_year"].tolist())
        first["display_name"] = _map_group_display_name(group)
        first["base_display_name"] = first["display_name"]
        first["sector"] = _join_unique_text(group["sector"].tolist(), fallback=str(first.get("sector", "")))
        first["subcarrier"] = _join_unique_text(group["subcarrier"].tolist(), fallback=str(first.get("subcarrier", "")))
        first["bus_summary"] = _join_unique_text(group["connection_buses"].tolist())
        first["connection_buses"] = _unique_preserve(
            bus for buses in group["connection_buses"].tolist() for bus in (buses if isinstance(buses, list) else [])
        )
        first["capacity"] = _map_group_capacity_summary(group)
        first["source"] = _join_unique_text(group["source"].tolist(), fallback=str(first.get("source", "")))
        first["accuracy_m"] = _join_unique_text(group["accuracy_m"].tolist(), fallback=str(first.get("accuracy_m", "")))
        first["crs"] = _join_unique_text(group["crs"].tolist(), fallback=str(first.get("crs", MAP_CRS_EPSG)))
        first["coordinate_epoch"] = _join_unique_text(
            group["coordinate_epoch"].tolist(),
            fallback=str(first.get("coordinate_epoch", "")),
        )
        first["component_count"] = int(len(group))
        first["component_details"] = "<br>".join(group.apply(_map_detail_line, axis=1).tolist())
        first["marker_size"] = int(pd.to_numeric(group["marker_size"], errors="coerce").fillna(12).max())
        first["marker_symbol"] = _map_layer_symbol(first.get("map_layer_key", ""), first.get("layer_label", ""))
        first = first.drop(labels=[c for c in ("_group_lon", "_group_lat", "_group_base") if c in first.index])
        rows.append(first)

    return pd.DataFrame(rows)


def build_map_component_table(n: pypsa.Network) -> pd.DataFrame:
    """
    Überführt georeferenzierte PyPSA-Komponenten in eine einheitliche Kartentabelle.

    Komponenten ohne gültige Koordinate oder ohne relevante Leistung / Aktivität
    werden nicht aufgenommen, damit die Karte nur interpretierbare Objekte zeigt.

    Inputs: PyPSA-Netzwerk.
    Outputs: Kartentabelle als DataFrame.
    """
    if n is None:
        return pd.DataFrame()

    years_set = set(get_investment_years(n))
    rows = []

    for component, layer_label, singular, color, marker_size in MAP_LAYER_DEFS:
        df = getattr(n, component, None)
        if df is None or df.empty:
            continue

        for name, r in df.iterrows():
            bus_names = _component_bus_names(component, r)
            lon, lat = _row_lon_lat(r)
            source = _text_or_default(r.get("location_source"), MAP_DEFAULT_SOURCE)
            accuracy = _text_or_default(r.get("location_accuracy_m"), "")
            crs = _text_or_default(r.get("crs_epsg"), MAP_CRS_EPSG)
            epoch = _text_or_default(r.get("coordinate_epoch"), "")

            if lon is None or lat is None:
                continue

            sector, subcarrier = _map_component_sector(n, component, r)
            base_name, build_year = split_base_and_year(str(name), years_set)
            display_name = _text_or_default(r.get("map_label"), strip_prefix(name))
            map_layer_key, layer_label, singular, color, marker_size = _map_technology_layer(component, str(name), r)
            marker_symbol = _map_layer_symbol(map_layer_key, layer_label)
            rows.append({
                "component": component,
                "component_id": f"{component}|{name}",
                "map_layer_key": map_layer_key,
                "layer_label": layer_label,
                "display_type": singular,
                "marker_symbol": marker_symbol,
                "name": str(name),
                "base_name": base_name,
                "build_year": build_year if build_year is not None else "",
                "display_name": display_name,
                "base_display_name": _map_base_display_name(base_name),
                "lon": float(lon),
                "lat": float(lat),
                "sector": sector,
                "subcarrier": subcarrier,
                "bus_summary": ", ".join(bus_names),
                "connection_buses": bus_names,
                "capacity": _map_capacity_text(component, r),
                "source": source,
                "accuracy_m": accuracy,
                "crs": crs,
                "coordinate_epoch": epoch,
                "marker_color": color,
                "marker_size": marker_size,
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = filter_map_existing_components(n, out)
    if out.empty:
        return out
    out["_layer_order"] = out.apply(
        lambda row: _map_layer_order_value(str(row.get("map_layer_key", "")), str(row.get("component", ""))),
        axis=1,
    ).astype(int)
    out = out.sort_values(["_layer_order", "display_name", "name"]).drop(columns=["_layer_order"])
    return out


def filter_map_components_for_period(df_map: pd.DataFrame, df_life: pd.DataFrame, period_value) -> pd.DataFrame:
    """
    Beschränkt die Kartentabelle auf Komponenten, die in der gewählten Periode aktiv sind.

    Inputs: Kartentabelle, Lebensdauertabelle und Periodenauswahl.
    Outputs: gefilterte Kartentabelle.
    """
    if df_map is None or df_map.empty:
        return pd.DataFrame()
    if period_value is None or str(period_value) == "all":
        return df_map.copy()
    if df_life is None or df_life.empty:
        return df_map.copy()

    active_set = active_assets_in_period(df_life, period_value)
    if {"component", "name"}.issubset(df_life.columns):
        assets_with_life = set(zip(df_life["component"].astype(str), df_life["name"].astype(str)))
    else:
        assets_with_life = set()

    keep = []
    for _, row in df_map.iterrows():
        comp = str(row.get("component", ""))
        name = str(row.get("name", ""))
        if (comp, name) not in assets_with_life:
            keep.append(True)
        else:
            keep.append((comp, name) in active_set)
    return df_map.loc[keep].copy()


def build_map_component_options(df_map: pd.DataFrame) -> list[dict]:
    """
    Erzeugt die Optionen des Komponentenfilters für die Systemkarte.
    
    Inputs: df_map.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    if df_map is None or df_map.empty:
        return []
    options = []
    for _, row in df_map.iterrows():
        label = f"{row['layer_label']}: {row['display_name']}"
        options.append({"label": label, "value": row["component_id"]})
    return options


def prepare_map_components_for_plot(df_map: pd.DataFrame, aggregate_overlapping_points: bool = True) -> pd.DataFrame:
    """
    Sortiert und verdichtet Kartenpunkte über gleiche Ebenen und selbe Koordinate.

    Inputs: Kartentabelle und Aggregationsschalter.
    Outputs: vorbereitete Kartentabelle für die Leaflet-Darstellung.
    """
    if df_map is None or df_map.empty:
        return pd.DataFrame()

    out = df_map.copy()
    if aggregate_overlapping_points:
        out = aggregate_map_overlapping_components(out)
    else:
        out["component_count"] = 1
        out["component_details"] = out.apply(_map_detail_line, axis=1)
    if out.empty:
        return out
    out["_layer_order"] = out.apply(
        lambda row: _map_layer_order_value(str(row.get("map_layer_key", "")), str(row.get("component", ""))),
        axis=1,
    ).astype(int)
    out = out.sort_values(["_layer_order", "display_name", "name"]).drop(columns=["_layer_order"])
    return out


def _map_zoom_from_extent(df_map: pd.DataFrame) -> float:
    """
    Legt fest, wie stark die Systemkarte am Anfang gezoomt sein soll.
    
    Inputs: df_map.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    if df_map is None or df_map.empty:
        return 13.0
    lat_span = float(df_map["lat"].max() - df_map["lat"].min())
    lon_span = float(df_map["lon"].max() - df_map["lon"].min())
    span = max(lat_span, lon_span)
    if span < 0.002:
        return 16.0
    if span < 0.01:
        return 14.0
    if span < 0.05:
        return 12.0
    if span < 0.5:
        return 10.0
    return 6.0


def _leaflet_empty_map_html(title: str, message: str) -> str:
    """
    Baut eine kleine Ersatz-HTML-Seite für die Karte, wenn keine Kartendaten vorhanden sein sollten.
    
    Inputs: title, message.
    Outputs: HTML-String oder HTML-Layoutbaustein.
    """
    title_safe = html_escape(str(title))
    message_safe = html_escape(str(message))
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    html, body {{
      height: 100%;
      margin: 0;
      font-family: Arial, sans-serif;
      color: #1f3555;
    }}
    .empty-map {{
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      background: #f7f8fb;
      border: 1px solid #d8dde8;
      box-sizing: border-box;
    }}
    .empty-map h3 {{ margin: 0 0 10px 0; }}
  </style>
</head>
<body>
  <div class="empty-map">
    <div>
      <h3>{title_safe}</h3>
      <div>{message_safe}</div>
    </div>
  </div>
</body>
</html>"""


def build_network_map_html(
    n: pypsa.Network,
    df_life: pd.DataFrame,
    selected_components,
    period_value="all",
) -> str:
    """
    Erstellt das vollständige Leaflet-HTML für die Systemkarte.

    Das HTML enthält Kartentitel, Marker, Ebenenfilter, OpenStreetMap-Lizenz und
    Fallback-Hinweise, falls keine darstellbaren Komponenten vorhanden sind.

    Inputs: PyPSA-Netzwerk, Lebensdauertabelle, Komponentenauswahl und Periode.
    Outputs: vollständiger HTML-String für das Karten-Iframe.
    """
    if n is None:
        return _leaflet_empty_map_html("Systemkarte", "Keine Datenbasis geladen.")

    df_map_all = build_map_component_table(n)
    if df_map_all.empty:
        return _leaflet_empty_map_html(
            "Systemkarte",
            "Keine darstellbaren Komponenten gefunden. Bitte Geokoordinaten und Leistungen / Kapazitäten > 0 in der .nc-Datei prüfen.",
        )

    df_map = filter_map_components_for_period(df_map_all, df_life, period_value)
    component_set = set(selected_components or [])
    if component_set:
        df_map = df_map[df_map["component_id"].isin(component_set)].copy()
    if df_map.empty:
        return _leaflet_empty_map_html("Systemkarte", "Keine Komponenten für die aktuelle Auswahl.")

    df_plot = prepare_map_components_for_plot(df_map, aggregate_overlapping_points=True)
    if df_plot.empty:
        return _leaflet_empty_map_html("Systemkarte", "Keine Komponenten für die aktuelle Auswahl.")

    df_plot = df_plot.copy()
    df_plot["_layer_order"] = df_plot.apply(
        lambda row: _map_layer_order_value(str(row.get("map_layer_key", "")), str(row.get("component", ""))),
        axis=1,
    ).astype(int)
    df_plot = df_plot.sort_values(["_layer_order", "display_name", "name"]).drop(columns=["_layer_order"])

    markers = []
    for _, row in df_plot.iterrows():
        layer_key = str(row.get("map_layer_key", ""))
        layer_label = _text_or_default(row.get("layer_label"), layer_key)
        symbol = _text_or_default(row.get("marker_symbol"), _map_layer_symbol(layer_key, layer_label))
        markers.append({
            "lat": float(row.get("lat")),
            "lon": float(row.get("lon")),
            "layerKey": layer_key,
            "layerLabel": layer_label,
            "legendLabel": f"{symbol} {layer_label}".strip(),
            "symbol": symbol,
            "color": _text_or_default(row.get("marker_color"), "#555"),
            "iconUrl": _map_icon_asset_url(layer_key),
            "popup": _map_popup_html(row),
        })

    center_lat = float(df_plot["lat"].mean())
    center_lon = float(df_plot["lon"].mean())
    zoom = _map_zoom_from_extent(df_plot)
    title = "Systemkarte - Komponenten"
    if period_value is not None and str(period_value) != "all":
        title += f" - aktive Komponenten {period_value}"
    title += f" ({MAP_CRS_EPSG}, {MAP_AXIS_ORDER})"

    payload = {
        "title": title,
        "center": [center_lat, center_lon],
        "zoom": zoom,
        "markers": markers,
        "iconSize": MAP_ICON_SIZE_PX,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lora:wght@500;600;700&family=Open+Sans:wght@400;600;700&display=swap">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    html, body, #map {{
      height: 100%;
      width: 100%;
      margin: 0;
      padding: 0;
      font-family: "Open Sans", Arial, sans-serif;
    }}
    .map-title {{
      position: absolute;
      top: 10px;
      left: 58px;
      z-index: 900;
      padding: 6px 10px;
      background: rgba(255,255,255,0.86);
      border: 1px solid rgba(0,0,0,0.16);
      border-radius: 3px;
      color: #1f3555;
      font-family: "Lora", Georgia, serif;
      font-size: 16px;
    }}
    .leaflet-control-layers {{
      background: rgba(255,255,255,0.86);
      color: #1f3555;
    }}
    .leaflet-popup-content {{
      min-width: 280px;
      max-width: 520px;
      line-height: 1.35;
      color: #1f3555;
    }}
    .map-text-icon {{
      border: 2px solid currentColor;
      border-radius: 999px;
      background: rgba(255,255,255,0.92);
      box-shadow: 0 1px 4px rgba(0,0,0,0.35);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 11px;
      line-height: 1;
      box-sizing: border-box;
    }}
    .leaflet-icon-png {{
      filter: drop-shadow(0 1px 3px rgba(0,0,0,0.45));
    }}
    .legend-icon-img {{
      width: 45px;
      height: 45px;
      object-fit: contain;
      vertical-align: middle;
      margin-right: 10px;
    }}
    .legend-icon-text {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 22px;
      height: 18px;
      margin-right: 6px;
      border-radius: 999px;
      border: 1px solid currentColor;
      background: rgba(255,255,255,0.9);
      font-size: 10px;
      font-weight: 700;
      vertical-align: middle;
    }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="map-title" id="map-title"></div>
  <script>
    const payload = {payload_json};
    const map = L.map("map", {{ zoomControl: true }}).setView(payload.center, payload.zoom);
    L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 19,
      attribution: "Kartendaten &copy; <a href='{OSM_COPYRIGHT_URL}' target='_blank' rel='noopener noreferrer'>OpenStreetMap-Mitwirkende</a> | Darstellung mit Leaflet",
      crossOrigin: true
    }}).addTo(map);
    document.getElementById("map-title").textContent = payload.title;

    const layerGroups = {{}};
    const overlays = {{}};

    function escapeHtml(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function layerControlLabel(marker) {{
      if (marker.iconUrl) {{
        return `<img class="legend-icon-img" src="${{marker.iconUrl}}" alt="">${{escapeHtml(marker.layerLabel)}}`;
      }}
      return `<span class="legend-icon-text" style="color:${{marker.color}}">${{escapeHtml(marker.symbol)}}</span>${{escapeHtml(marker.layerLabel)}}`;
    }}

    function markerIcon(marker) {{
      const size = Number(payload.iconSize || 30);
      if (marker.iconUrl) {{
        return L.icon({{
          iconUrl: marker.iconUrl,
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2],
          popupAnchor: [0, -size / 2],
          className: "leaflet-icon-png"
        }});
      }}
      return L.divIcon({{
        className: "map-text-icon",
        html: `<span>${{escapeHtml(marker.symbol)}}</span>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        popupAnchor: [0, -size / 2],
      }});
    }}

    for (const marker of payload.markers) {{
      if (!layerGroups[marker.layerKey]) {{
        layerGroups[marker.layerKey] = L.layerGroup().addTo(map);
        overlays[layerControlLabel(marker)] = layerGroups[marker.layerKey];
      }}
      const leafletMarker = L.marker([marker.lat, marker.lon], {{
        icon: markerIcon(marker),
        title: marker.layerLabel,
      }});
      if (!marker.iconUrl) {{
        leafletMarker.on("add", function() {{
          const el = this.getElement();
          if (el) el.style.color = marker.color;
        }});
      }}
      leafletMarker.bindPopup(marker.popup, {{ maxWidth: 560 }});
      leafletMarker.addTo(layerGroups[marker.layerKey]);
    }}

    L.control.layers(null, overlays, {{
      collapsed: false,
      position: "topleft"
    }}).addTo(map);
    setTimeout(() => map.invalidateSize(), 150);
  </script>
</body>
</html>"""


#%% Helper: Jahresfilter für Nennleistungen / Kapazitäten


def _filter_df_sector_years(df_sector: pd.DataFrame, selected_years, years_all: list[int]) -> tuple[pd.DataFrame, list[int]]:
    """
    Filtert einen sektorspezifischen DataFrame nach ausgewählten Investitionsperioden (Jahre).
    
    Inputs: df_sector: Sektoren-DataFrame mit Spalte "year"
            selected_years: Iterable (z. B. aus Dropdown)
            years_all: list[int] aller vorhandenen Jahre im Dataset.
            
    Wenn keine MIP-Jahre vorhanden: gibt DF unverändert zurück.
    Wenn selected_years leer: gibt leeres DF zurück.
    Konvertiert selected_years robust nach int.
    Filtert df_sector['year'] auf die Schnittmenge.
    
    Outputs: tuple[DataFrame, list[int]]: (gefiltertes DF, gefilterte Jahre).
    """
    if df_sector is None or df_sector.empty:
        return df_sector, years_all

    if not years_all:
        return df_sector, years_all  # Single-year: keine Filterung

    if not selected_years:
        return df_sector.iloc[0:0].copy(), []

    sel = []
    for y in selected_years:
        try:
            sel.append(int(y))
        except Exception:
            pass

    years_f = [y for y in years_all if y in set(sel)]
    if not years_f:
        return df_sector.iloc[0:0].copy(), []

    dff = df_sector.copy()
    dff = dff[dff["year"].astype(int).isin(years_f)]
    return dff, years_f

#%% Helper: Capacities auf aktive Assets statt neugebaute Assets beziehen

def expand_caps_to_active_periods(
    df_caps: pd.DataFrame,
    df_life: pd.DataFrame,
    years: list[int],
    value_col: str = "p_nom",
) -> pd.DataFrame:
    """
    Transformiert 'Zubau je Build' in 'aktive Kapazität je Investitionsperiode' unter
    Berücksichtigung von build_year und end_year (Lifetime).
    
    Inputs: df_caps: DataFrame mit Kapazitätswerten (z.B. p_nom/e_nom) und Spalten: 
            component,name
            df_life: DataFrame mit Lebensdauerinformationen: component, name, 
            build_year, end_year.
            years: list[int] Investitionsperioden.
            value_col: Spaltenname der Kapazität (Default 'p_nom')
    
    Single-year: ergänzt 'year' als leerer String und gibt DF zurück.
    Merged df_caps mit df_life (left join).
    Fallback: fehlende build_year -> horizon_start; end_year -> inf.
    Mappt build_year auf nächste Investitionsperiode (build_period).
    Erzeugt je Periode p alle Anlagen, die build_period <= p < end_year erfüllen.
    Verkettung der Teilmengen; bereinigt Hilfsspalten.
    
    Outputs: DataFrame: Erweiterte Tabelle mit zusätzlicher Spalte 'year'.
        
    """
    if df_caps is None or df_caps.empty:
        return df_caps

    # Single-year: keine Werte zur Verarbeitung
    if not years:
        out = df_caps.copy()
        out["year"] = ""
        return out

    # Life-Map
    life_cols = ["component", "name", "build_year", "end_year"]
    life = df_life[life_cols].copy() if (df_life is not None and not df_life.empty) else pd.DataFrame(columns=life_cols)

    d = df_caps.copy()
    d = d.merge(life, on=["component", "name"], how="left")

    # Fallbacks, wenn build/end fehlen (z.B. keine lifetime/build_year gesetzt)
    horizon_start = int(min(years))
    d["build_year"] = pd.to_numeric(d["build_year"], errors="coerce").fillna(horizon_start).astype(int)
    d["end_year"] = pd.to_numeric(d["end_year"], errors="coerce")
    d["end_year"] = d["end_year"].where(np.isfinite(d["end_year"]), np.inf)
    d["end_year"] = d["end_year"].fillna(np.inf)

    # Optional: falls build_year nicht exakt auf einer Investitionsperiode liegt, auf nächste Periode mappen
    years_sorted = sorted(int(y) for y in years)

    def map_to_period(by: int) -> int:
        """
        Hilfsfunktion für die Systemkarte: bereitet map to period auf.
        
        Inputs: by.
        Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
        """
        if by in years_sorted:
            return by
        future = [y for y in years_sorted if y >= by]
        return future[0] if future else years_sorted[-1]

    d["build_period"] = d["build_year"].apply(map_to_period).astype(int)

    # Expand: jede Zeile in jede Periode, in der sie aktiv ist
    parts = []
    for p in years_sorted:
        m = d[(d["build_period"] <= p) & (p < d["end_year"])].copy()
        if m.empty:
            continue
        m["year"] = int(p)
        parts.append(m)

    if not parts:
        out = d.iloc[0:0].copy()
        out["year"] = []
        return out

    out = pd.concat(parts, ignore_index=True)
    out = out.drop(columns=["build_period"], errors="ignore")
    return out



#%% Zeitreihen: Aufbau (dyn -> df_dyn_all + meta)


def _timestep_and_period_from_df(df: pd.DataFrame):
    """
    Extrahiert aus einem Zeitreihen-DataFrame den Zeitschritt-Index und optional die
    Investitionsperiode.
    
    Inputs: df: DataFrame mit Zeitindex, ggf. MultiIndex (period, snapshot) oder Tuple-Index
    
    Wenn MultiIndex: timestep = letzter Level, period = Level 0
    Wenn Tuple-Index: timestep = letzter Tuple-Teil, period = erster Tuple-Teil
    Sonst: timestep = Index, period = None
    
    Outputs: (pd.Index timestep, pd.Series|None period)
    """
    idx = df.index

    if isinstance(idx, pd.MultiIndex):
        period = idx.get_level_values(0)
        timestep = idx.get_level_values(-1)
        return pd.Index(timestep, name="timestep"), pd.Series(period, name="period")

    # Tuple-Index abfangen
    if len(idx) > 0 and isinstance(idx[0], tuple) and len(idx[0]) >= 2:
        period = [t[0] for t in idx]
        timestep = [t[-1] for t in idx]  # typischerweise Timestamp
        return pd.Index(timestep, name="timestep"), pd.Series(period, name="period")

    return pd.Index(idx, name="timestep"), None



def _nonempty_bus_mask(s: pd.Series) -> pd.Series:
    """
    Hilfsfunktion: erzeugt eine Maske für nicht-leere Bus-Strings in einer Series.
    
    Inputs: s: pd.series
    
    Konvertiert nach String-Dtype, prüft notna und strip != ''
    
    Outputs: pd.Series[bool]: True für gültige Busnamen.

    """
    s2 = s.astype("string")
    return s2.notna() & (s2.str.strip() != "")


def get_existing_link_ports(n: pypsa.Network, max_i: int = 9) -> list[int]:
    """
    Ermittelt, welche Link-Ports (bus0..busN) im Netzwerk tatsächlich belegt sind.
    
    Inputs: · n: pypsa.Network
              max_i: int (Default 9)
              
    Startet immer mit Port 0.
    Prüft für i=1..max_i, ob Spalte bus{i} existiert und mindestens ein nicht-leerer Eintrag
    vorhanden ist
    
    Outputs: list[int]: Liste der existierenden Ports
    """
    ports = [0]
    if not hasattr(n, "links") or n.links.empty:
        return ports
    df = n.links
    for i in range(1, max_i + 1):
        col = f"bus{i}"
        if col in df.columns and _nonempty_bus_mask(df[col]).any():
            ports.append(i)
    return ports


def links_with_bus_i(n: pypsa.Network, i: int) -> list[str]:
    """
    Gibt die Namen der Links zurück, für die bus{i} gesetzt ist (für i=0 und i=1 alle Links).
    
    Inputs: n: pypsa.Network
            i: int
            
    Für i=0: alle Link-Indizes.
    Für i>0: filtert n.links nach nicht-leeren bus{i}.
    
    Outputs: list[str]: Link-Namen
    """
    if i == 0:
        return list(n.links.index)
    col = f"bus{i}"
    if col not in n.links.columns:
        return []
    return n.links.index[_nonempty_bus_mask(n.links[col])].astype(str).tolist()


def build_dynamic_timeseries_df(
    n: pypsa.Network,
    components=None,
    add_component_prefix: bool = False,
    make_link_line_ports_positive: bool = True,
) -> pd.DataFrame:
    """
    Baut einen  Zeitreihen-DataFrame aus dynamischen PyPSA-Komponenten
    (links/generators/loads/stores/storage_units/lines) inklusive Periode.
    
    Inputs: n: pypsa.Network
            components: Liste der zu verarbeitenden Komponenten (Default: typische Komponenten)
            add_component_prefix: wenn True, Spaltenformat 'component__asset_attr', 
            sonst asset_attr
            make_link_line_ports_positive: wenn True, nimmt abs() für p-Ports von links/lines
    
    Iteriert über Komponenten und wählt pro Komponente geeignete Attribute (p, p_set, p0...pn)
    Für Links: berücksichtigt nur Ports, deren bus{i} gesetzt ist und filtert die Spalten
    entsprechend
    Normalisiert Index über _timestep_and_period_from_df (timestep als Index; period in
    separater Series)
    Benennung der Spalten nach Standard 'Komponententyp__Komponentenname_Variable'
    Verkettung nach Attributblöcken (p0,p1,... zuerst)
    Fügt 'period' ein (oder Platzhalter) und setzt Index als Spalte 'timestep' (reset_index)
    
    Outputs: DataFrame: Spalten 'period', 'timestep' plus Zeitreihen-Spalten.
    """

    if components is None:
        components = ["links", "generators", "loads", "stores", "storage_units", "lines"]

    frames_by_attr = {}
    period_series = None

    for comp_name in components:
        if not hasattr(n, "components") or not hasattr(n.components, comp_name):
            continue
        if not hasattr(n, comp_name):
            continue

        # dynamische tables: via n.components API (wie in deinem Stand), aber abgesichert
        if not hasattr(n, "components") or not hasattr(n.components, comp_name):
            continue
        comp = getattr(n.components, comp_name)
        dyn = comp.dynamic

        if comp_name == "links":
            ports = get_existing_link_ports(n, max_i=9)
            attrs = [f"p{i}" for i in ports if f"p{i}" in dyn]
        elif comp_name == "lines":
            attrs = [a for a in ("p0", "p1") if a in dyn]
        else:
            if "p" in dyn:
                attrs = ["p"]
            elif "p_set" in dyn:
                attrs = ["p_set"]
            else:
                attrs = []

        for attr in attrs:
            df = dyn.get(attr)
            if df is None or df.shape[1] == 0:
                continue

            df2 = df.copy()

            # Links: nur echte Ports (bus{i} gesetzt)
            if comp_name == "links" and re.match(r"^p(\d+)$", str(attr)):
                i = int(re.match(r"^p(\d+)$", str(attr)).group(1))
                valid = set(links_with_bus_i(n, i))
                if not valid:
                    continue
                df2 = df2.loc[:, [c for c in df2.columns.astype(str) if c in valid]]
                if df2.shape[1] == 0:
                    continue

            t_idx, p_ser = _timestep_and_period_from_df(df2)
            df2.index = t_idx

            if p_ser is not None and period_series is None:
                period_series = pd.Series(p_ser.values, index=t_idx, name="period")

            if make_link_line_ports_positive and comp_name in ("links", "lines") and re.match(r"^p\d+$", str(attr)):
                df2 = df2.abs()
            # Spaltenbenennung für die Zeitreihen "Komponententyp__Komponentenname_Variable"
            if add_component_prefix:
                df2.columns = [f"{comp_name}__{col}_{attr}" for col in df2.columns]
            else:
                df2.columns = [f"{col}_{attr}" for col in df2.columns]

            frames_by_attr.setdefault(attr, []).append(df2)

    if not frames_by_attr:
        return pd.DataFrame(columns=["period", "timestep"])

    port_attrs = sorted([a for a in frames_by_attr.keys() if re.match(r"^p\d+$", a)], key=lambda s: int(s[1:]))
    other_attrs = [a for a in frames_by_attr.keys() if a not in port_attrs]
    attr_order = port_attrs + other_attrs

    parts = []
    for a in attr_order:
        part = pd.concat(frames_by_attr[a], axis=1)
        part = part.reindex(columns=sorted(part.columns))
        parts.append(part)

    out = pd.concat(parts, axis=1)

    if period_series is not None:
        out.insert(0, "period", period_series.loc[out.index].values)
    else:
        out.insert(0, "period", "Nur ein Zeitraum vorhanden")

    out = out.reset_index()  # timestep wird zur Spalte
    return out


def infer_internal_store_buses(n: pypsa.Network) -> set[str]:
    """
    Identifiziert Busse, die nur von Stores genutzt werden (interne Speicherbusse), um sie z.B.
    aus bestimmten Plots auszuschließen.
    
    Inputs: n: pypsa.Network
    
    Sammelt Busse aus Stores.
    Sammelt Systembusse aus Loads, Generators, Storage Units.
    Gibt Store-Busse zurück, die nicht in den Systembussen vorkommen.
    
    Outputs: set[str]: interne Store-Buses
    """
    if not hasattr(n, "buses") or n.buses.empty:
        return set()

    store_buses = set()
    if hasattr(n, "stores") and not n.stores.empty and "bus" in n.stores.columns:
        store_buses = set(n.stores["bus"].dropna().astype(str))

    if not store_buses:
        return set()

    load_buses = set(n.loads["bus"].dropna().astype(str)) if hasattr(n, "loads") and not n.loads.empty and "bus" in n.loads.columns else set()
    gen_buses  = set(n.generators["bus"].dropna().astype(str)) if hasattr(n, "generators") and not n.generators.empty and "bus" in n.generators.columns else set()
    su_buses   = set(n.storage_units["bus"].dropna().astype(str)) if hasattr(n, "storage_units") and not n.storage_units.empty and "bus" in n.storage_units.columns else set()

    system_buses = load_buses | gen_buses | su_buses
    return {b for b in store_buses if b not in system_buses}


def parse_ts_col(col: str):
    """
    Parst eine Zeitreihen-Spaltenbezeichnung im Format 'component__asset_attr' in
    (component, asset, attr).
    
    Inputs: col: str
    
    Splittet an '__'.
    Splittet Rest an letztem '_' (rsplit) in asset und attr.
    Gibt None zurück, wenn Format nicht passt.
    
    Outputs: tuple[str,str,str] | None
    """
    if "__" not in col:
        return None
    comp, rest = col.split("__", 1)
    if "_" not in rest:
        return None
    asset, attr = rest.rsplit("_", 1)
    return comp, asset, attr


def infer_bus_for_timeseries(n: pypsa.Network, comp: str, asset: str, attr: str):
    """
    Leitet aus (component, asset, attr) den zugehörigen Bus ab (insb. für Link-Ports bus{i})
    
    Inputs: n: pypsa.Network
            comp: str
            asset: str
            attr: str
            
    Für links/lines und attr 'p{i}': nutzt bus{i}
    Sonst: nutzt generisches 'bus'-Feld der statischen Tabelle, falls vorhanden
    
    Outputs: bus[str] oder None
    """
    m = re.match(r"^p(\d+)$", str(attr))
    if comp in ("links", "lines") and m:
        i = int(m.group(1))
        df = getattr(n, comp, None)
        if df is None or asset not in df.index:
            return None
        bus_col = f"bus{i}"
        if bus_col in df.columns:
            b = df.at[asset, bus_col]
            return None if pd.isna(b) else b
        return None

    df = getattr(n, comp, None)
    if df is None or df.empty or asset not in df.index:
        return None
    if "bus" in df.columns:
        b = df.at[asset, "bus"]
        return None if pd.isna(b) else b
    return None


def build_timeseries_meta(n: pypsa.Network, df_dyn_all: pd.DataFrame, internal_store_buses: set[str]) -> pd.DataFrame:
    """
    Erstellt Metadaten pro Zeitreihen-Spalte: Komponente, Asset, Attr, Bus, Sektor/Subcarrier
    sowie Flag für interne Speicherbuses.
    
    Inputs: n: pypsa.Network
            df_dyn_all: DataFrame aus build_dynamic_timeseries (flat)
            internal_store_buses: set[str] aus infer_internal_store_buses
    
    Iteriert über alle Spalten außer 'timestep'
    Parst Spaltennamen via parse_ts_col; überspringt unpassende Spalten
    Leitet Bus per infer_bus_for_timeseries ab
    Bestimmt sector/subcarrier über sector_subcarrier_from_bus
    Markiert Busse, die als internal_store_buses erkannt wurden
    Setzt Index der Meta-Tabelle auf die Spaltennamen ('col')
    
    Outputs: DataFrame: Meta-Table mit Index "coL"
    """
    cols = [c for c in df_dyn_all.columns if c != "timestep"]
    rows = []
    for col in cols:
        parsed = parse_ts_col(col)
        if parsed is None:
            continue
        comp, asset, attr = parsed
        bus = infer_bus_for_timeseries(n, comp, asset, attr)
        if comp == "links" and re.match(r"^p\d+$", str(attr)) and bus is None:
            continue

        sector, sub = sector_subcarrier_from_bus(n, bus)
        rows.append({
            "col": col,
            "component": comp,
            "asset": asset,
            "attr": attr,
            "bus": bus,
            "sector": sector,
            "subcarrier": sub,
            "is_internal_store_bus": (bus is not None and str(bus) in internal_store_buses)
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("col")


def insert_nan_breaks(data: pd.DataFrame, gap_factor: float = 3.0) -> pd.DataFrame:
    """
    Fügt NaN-Zeilen ein, um in Linienplots sichtbare Unterbrechungen bei großen Zeitsprüngen
    zu erzeugen.
    
    Inputs: data: DataFrame mit DatetimeIndex
            gap_factor: float (Default 3.0)
    
    Berechnet Zeitdifferenzen zwischen Zeitschritten
    Ermittelt mediane Schrittweite (step) und definiert gap_threshold = step*gap_factor
    Für Deltas > threshold: fügt einen NaN-Zeitpunkt unmittelbar vor der Lücke ein
    Verkettung und Sortierung
    
    Outputs: DataFrame wie Input, nur ergänzt um NaN-Zeilen
    """
    data = data.sort_index()
    dt = data.index.to_series().diff()
    dt_pos = dt[dt > pd.Timedelta(0)]
    if dt_pos.empty:
        return data

    step = dt_pos.median()
    gap_threshold = step * gap_factor
    gap_mask = dt > gap_threshold
    if not gap_mask.any():
        return data

    break_times = data.index[gap_mask] - pd.Timedelta("1ns")
    break_times = break_times[~break_times.isin(data.index)]
    if len(break_times) == 0:
        return data

    breaks = pd.DataFrame(np.nan, index=break_times, columns=data.columns)
    breaks = breaks.astype(data.dtypes.to_dict(), errors="ignore")
    return pd.concat([data, breaks], axis=0).sort_index()


def build_sector_timeseries_fig(
    df_dyn_all: pd.DataFrame,
    meta: pd.DataFrame,
    sector: str,
    unit: str = "kW",
    max_traces: int = 30,
    default_component_visible: str = "generators",
    ts_color_map: dict[str, str] | None = None,
) -> go.Figure:
    """
    Erstellt ein Plotly-Linienplot für Zeitreihen eines Sektors, 
    inkl. Hover-Infos und optionaler Farbzuteilung.
    
    Inputs: df_dyn_all: DataFrame mit 'timestep' und Zeitreihen-Spalten
            meta: Meta-DataFrame (Index = Spaltennamen) aus build_timeseries_meta
            sector: 'Strom'/'Wärme'/'Sonstige'
            unit: String, z.B. 'kW'
            max_traces: maximale Anzahl dargestellter Zeitreihen (Top-N nach Peak)
            default_component_visible: welche Komponente standardmäßig sichtbar ist,
            andere "legendonly"
            ts_color_map: optional dict col->color
    
    Filtert meta nach sektor und blendet interne Store-Link-Busse aus
    Zieht entsprechende Spalten aus df_dyn_all und setzt DatetimeIndex
    Sortiert, fügt NaN-Breaks ein
    Rangiert Spalten nach absolutem Peak und wählt Top-N
    Erzeugt pro Spalte eine Scatter-Linie mit Hovertemplate (Asset, Subcarrier, Variable)
    Konfiguriert Achsen, Titel und Legende
    
    Outputs: go.figure: Plotly-Abbildung
    """

    fig = go.Figure()

    if meta is None or meta.empty or "timestep" not in df_dyn_all.columns:
        fig.update_layout(title=f"Zeitreihen ({sector}) (keine Daten)")
        return fig

    m = meta[meta["sector"] == sector].copy()
    m = m[~((m["component"] == "links") & (m["is_internal_store_bus"] == True))]

    cols = m.index.tolist()
    if not cols:
        fig.update_layout(title=f"Zeitreihen ({sector}) (keine Daten)")
        return fig

    t = pd.to_datetime(df_dyn_all["timestep"])
    data = df_dyn_all[cols].copy()
    data.index = t
    data = data.sort_index()
    if data.empty:
        fig.update_layout(title=f"Zeitreihen ({sector}) (keine Daten)")
        return fig

    data = insert_nan_breaks(data, gap_factor=3.0)

    peak = data.abs().max().sort_values(ascending=False)
    cols_sorted = peak.index.tolist()
    cols_plot = cols_sorted[:max_traces] if (max_traces is not None and len(cols_sorted) > max_traces) else cols_sorted

    for col in cols_plot:
        comp = col.split("__", 1)[0] if "__" in col else ""
        vis = True if comp == default_component_visible else "legendonly"

        asset = meta.at[col, "asset"] if col in meta.index else strip_prefix(col)
        attr  = meta.at[col, "attr"]  if col in meta.index else ""

        sc = None
        if col in meta.index and "subcarrier" in meta.columns:
            sc = meta.at[col, "subcarrier"]
            sc = DEFAULT_SUBCARRIER if pd.isna(sc) else str(sc)

        line_kwargs = {}
        if ts_color_map is not None:
            ccol = ts_color_map.get(str(col))
            if ccol:
                line_kwargs["color"] = ccol

        fig.add_trace(go.Scatter(
            name=asset,
            x=data.index,
            y=data[col].values,
            mode="lines",
            connectgaps=False,
            visible=vis,
            line=line_kwargs if line_kwargs else None,
            hovertemplate=(
                f"{asset}<br>"
                f"Energieträger: {sc if sc is not None else ''}<br>"
                f"Variable: {attr}<br>"
                "%{x}<br>%{y:.2f} " + unit +
                "<extra></extra>"
            )
        ))

    fig.update_layout(
        title=f"Zeitreihen ({sector})",
        xaxis_title="Zeit",
        yaxis_title=f"Leistung [{unit}]",
        legend_title="Komponente",
        margin=dict(l=30, r=30, t=60, b=50),
    )
    return fig

#%% Statische Tables + Kapazitäten + Ausbaupfad + Lifetime

def get_investment_years(n: pypsa.Network):
    """
    Liest Investitionsperioden (Jahre) aus einem PyPSA-Netzwerk, falls MIP aktiv ist.
    
    Inputs: n: pypsa.Network
    
    Wenn n.has_investment_periods True: gibt n.investment_periods als int-Liste zurück,
    sonst []
    
    Outputs: list[int]    
    """
    if getattr(n, "has_investment_periods", False):
        return [int(y) for y in list(n.investment_periods)]
    return []


def split_base_and_year(name: str, years_set: set[int]):
    """
    Trennt einen Namenssuffix '_YYYY' ab, wenn YYYY eine der Investitionsperioden ist.
    
    Inputs: name: str
            years_set: set[int]
            
    Regex sucht Suffix _[4 Zeichen]
    Wenn Jahr in years_set: gibt (basename, year) zurück, sonst (name, None)
    
    Outputs: (base_name: str, year: int|None)
    """
    name = str(name)
    m = re.search(r"_(\d{4})$", name)
    if m:
        y = int(m.group(1))
        if y in years_set:
            return name[:-5], y
    return name, None


def nominal_from_static(df_static: pd.DataFrame) -> pd.Series:
    """
    Liest aus einer statischen Komponententabelle den passenden Nennleistungs- bzw.
    Kapazitätsspaltenvektor
    
    Inputs: df_static: DataFrame
    
    Sucht in Reihenfolge p_nom_opt, p_nom, s_nom_opt, s_nom; sonst leere float-Serie
    
    Outputs: pd.Series: Nennleistungen / Kapazitäten
    """
    for col in ("p_nom_opt", "p_nom", "s_nom_opt", "s_nom"):
        if col in df_static.columns:
            return df_static[col]
    return pd.Series(index=df_static.index, dtype=float)


def _display_sector_subcarrier_for_power_row(
    component: str,
    name: str,
    sector: str,
    subcarrier: str,
) -> tuple[str, str]:
    """
    Ordnet technische Hilfsleitungen in Leistungs- und Ausbauauswertungen der fachlichen
    Ursprungstechnologie zu. Dadurch erscheinen PV- und BHKW-Exportpfade nicht zusätzlich
    als eigene Einspeise-Kategorie in der Legende.
    """
    component = str(component)
    name_text = str(name)
    if component == "links":
        if re.match(r"^PV_(?:Exportleitung|Stromnutzung)_", name_text, flags=re.IGNORECASE):
            return "Strom", "Strom_PV"
        if re.match(r"^BHKW_(?:Exportleitung|Stromnutzung)_", name_text, flags=re.IGNORECASE):
            return "Strom", "Strom_BHKW"
    return sector, subcarrier


def _bhkw_parent_capacity_by_build(n: pypsa.Network) -> dict[tuple[str, int], float]:
    """
    Liest die optimierte Leistung der eigentlichen BHKW-Komponenten aus. Diese Zuordnung wird
    genutzt, um reine BHKW-Hilfsleitungen auszublenden, wenn das zugehörige BHKW nicht gebaut
    wurde.
    """
    result: dict[tuple[str, int], float] = {}
    if not hasattr(n, "links") or n.links is None or n.links.empty:
        return result
    df = n.links
    nominal = nominal_from_static(df)
    for name in df.index:
        match = re.match(r"^BHKW_G(?P<group>\d+)_(?P<build>\d{4})$", str(name))
        if not match:
            continue
        value = pd.to_numeric(pd.Series([nominal.get(name, 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        result[(match.group("group"), int(match.group("build")))] = float(value)
    return result


def _is_inactive_bhkw_auxiliary(name: str, parent_caps: dict[tuple[str, int], float]) -> bool:
    """
    Erkennt BHKW-Stromnutzungs- und Exportleitungen, deren zugehörige BHKW-Anlage mit 0 kW
    optimiert wurde.
    """
    match = re.match(
        r"^BHKW_(?:Stromnutzung|Exportleitung)_G(?P<group>\d+)_(?P<build>\d{4})(?:_\d{4})?$",
        str(name),
        flags=re.IGNORECASE,
    )
    if not match:
        return False
    key = (match.group("group"), int(match.group("build")))
    if key not in parent_caps:
        return False
    return abs(float(parent_caps.get(key, 0.0))) <= CHART_EPS


def build_capacity_table(n: pypsa.Network) -> pd.DataFrame:
    """
    Erstellt eine tabellarische Übersicht der Nennleistungen je Asset, inkl. Ports (bei Links:
    in/out) und Zuordnung zu Sektor/Subcarrier
    
    Inputs: n: pypsa.Network
    
    Ermittelt MIP-Jahre und years_set
    Iteriert über generators, storage_units, links, sofern vorhanden
    Für generators/storage_units: p_nom aus nominal_from_static; Name -> (base, year) via
    split_base_and_year
    Für links: ermittelt bus0 (in) und bus1..bus9 (out) und berücksichtigt Effizienzen 
    (efficiency, efficiency2 etc.)
    Erzeugt Zeilen mit: sector, subcarrier, component, name, base_name, year, port, p_nom
    
    Outputs: DataFrame: Leistungstabelle (kW-bezogen, p_nom)
    """
    years = get_investment_years(n)
    years_set = set(years)
    rows = []
    bhkw_parent_caps = _bhkw_parent_capacity_by_build(n)

    if hasattr(n, "generators") and not n.generators.empty:
        df = n.generators
        p_nom = nominal_from_static(df).fillna(0.0)
        for name, r in df.iterrows():
            base, year = split_base_and_year(name, years_set)
            s, sc = sector_subcarrier_from_component_row(n, "generators", r)
            rows.append({
                "sector": s, "subcarrier": sc, "component": "generators",
                "name": str(name), "base_name": base, "year": year,
                "port": "p", "p_nom": float(p_nom.get(name, 0.0)),
            })

    if hasattr(n, "storage_units") and not n.storage_units.empty:
        df = n.storage_units
        p_nom = nominal_from_static(df).fillna(0.0)
        for name, r in df.iterrows():
            base, year = split_base_and_year(name, years_set)
            s, sc = sector_subcarrier_from_component_row(n, "storage_units", r)
            rows.append({
                "sector": s, "subcarrier": sc, "component": "storage_units",
                "name": str(name), "base_name": base, "year": year,
                "port": "p", "p_nom": float(p_nom.get(name, 0.0)),
            })

    if hasattr(n, "links") and not n.links.empty:
        df = n.links
        p_nom = nominal_from_static(df).fillna(0.0)
        for name, r in df.iterrows():
            if _is_inactive_bhkw_auxiliary(str(name), bhkw_parent_caps):
                continue
            base, year = split_base_and_year(name, years_set)
            p_in = float(p_nom.get(name, 0.0))

            bus0 = r.get("bus0")
            s0, sc0 = sector_subcarrier_from_bus(n, bus0)
            s0, sc0 = _display_sector_subcarrier_for_power_row("links", str(name), s0, sc0)
            rows.append({
                "sector": s0, "subcarrier": sc0, "component": "links",
                "name": str(name), "base_name": base, "year": year,
                "port": "in", "p_nom": p_in,
            })

            for i in range(1, 10):
                bus_col = f"bus{i}"
                if bus_col not in df.columns:
                    break
                bus_i = r.get(bus_col)
                if pd.isna(bus_i) or bus_i is None or str(bus_i).strip() == "":
                    continue

                eff_col = "efficiency" if i == 1 else f"efficiency{i}"
                eff = r.get(eff_col)
                eff = 1.0 if pd.isna(eff) else float(eff)

                si, sci = sector_subcarrier_from_bus(n, bus_i)
                si, sci = _display_sector_subcarrier_for_power_row("links", str(name), si, sci)
                rows.append({
                    "sector": si, "subcarrier": sci, "component": "links",
                    "name": str(name), "base_name": base, "year": year,
                    "port": f"out{i}", "p_nom": p_in * eff,
                })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["p_nom"] = out["p_nom"].fillna(0.0)
    out["subcarrier"] = out.get("subcarrier", DEFAULT_SUBCARRIER).fillna(DEFAULT_SUBCARRIER)
    link_mask = out["component"].astype(str).eq("links")
    if bool(link_mask.any()):
        link_rows = out[link_mask].copy()
        other_rows = out[~link_mask].copy()
        group_cols = ["sector", "subcarrier", "component", "name", "base_name", "year"]
        link_rows = (
            link_rows.groupby(group_cols, dropna=False, as_index=False)
            .agg({
                "p_nom": "max",
                "port": lambda values: ",".join(_unique_preserve([str(v) for v in values if str(v).strip()])),
            })
        )
        out = pd.concat([other_rows, link_rows], ignore_index=True, sort=False)
    return out


def prepare_multicategory(
    df_caps: pd.DataFrame,
    n: pypsa.Network,
    add_component_prefix: bool = True,
    value_col: str = "p_nom"
):
    """
    Bereitet Kapazitätstabellen für Plotly 'multicategory' x-Achsen auf (year, label), aggregiert
    nach (sector, subcarrier, year, label, component)
    
    Inputs: df_caps: DataFrame aus build_capacity_table oder build_energy_capacity_table 
                     (ggf. bereits erweitert)
                     n: pypsa.Network
                     add_component_prefix: ob label 'component__...' bekommt
                     value_col: zu aggregierende Spalte (p_nom oder e_nom)
                     
    Ermittelt years aus get_investment_years
    Sichert Spalte 'subcarrier' und setzt Defaults
    Baut label aus component/base_name/port
    Wenn years vorhanden: repliziert konstanten Bestand (year NaN) über alle Jahre
    Gruppiert und summiert value_col
    Teilt Ergebnis in dict je Sektor (SECTORS)
    Strippt Suffix "_sector", bei Links wird Subcarrier des entspr. Ports angehängt
    
    Outputs: (dict[str,DataFrame] by_sector, list[int] years)
    """
    years = get_investment_years(n)

    if df_caps is None or df_caps.empty or df_caps.shape[1] == 0:
        empty_cols = ["sector", "subcarrier", "year", "label", "component", value_col]
        result = {s: pd.DataFrame(columns=empty_cols) for s in SECTORS}
        return result, years

    df = df_caps.copy()

    if "subcarrier" not in df.columns:
        df["subcarrier"] = DEFAULT_SUBCARRIER
    df["subcarrier"] = df["subcarrier"].fillna(DEFAULT_SUBCARRIER).astype(str)

    def _label_suffix(value) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and pd.isna(value):
            return ""
        text = str(value).strip()
        return text

    def _build_label(row) -> str:
        base = strip_variable_suffix(row.get("base_name", ""))
        component = str(row.get("component", ""))

        if component == "links":
            sector_suffix = _label_suffix(row.get("sector"))
            carrier_suffix = _label_suffix(row.get("subcarrier"))
            if sector_suffix:
                if carrier_suffix and carrier_suffix != DEFAULT_SUBCARRIER:
                    core = f"{base}_{carrier_suffix}"
                else:
                    core = f"{base}_{sector_suffix}"
            else:
                port_suffix = _label_suffix(row.get("port"))
                core = f"{base}_{port_suffix}" if port_suffix else base
        else:
            core = base

        if add_component_prefix:
            return f"{component}__{core}"
        return core

    df["label"] = df.apply(_build_label, axis=1)

    if years:
        const = df[df["year"].isna()].copy()
        per = df[df["year"].notna()].copy()
        per["year"] = per["year"].astype(int)

        if not const.empty:
            const = const.drop(columns=["year"]).assign(_k=1)
            yrs = pd.DataFrame({"year": years, "_k": 1})
            const = const.merge(yrs, on="_k").drop(columns=["_k"])

        df2 = pd.concat([per, const], ignore_index=True)
    else:
        df2 = df.copy()
        df2["year"] = ""

    df2 = df2.groupby(["sector", "subcarrier", "year", "label", "component"], as_index=False)[value_col].sum()

    result = {}
    for sector in SECTORS:
        result[sector] = df2[df2["sector"] == sector].copy()
    return result, years


def build_sector_bar(
    df_sector: pd.DataFrame,
    sector: str,
    years,
    value_col: str,
    unit: str,
    title_prefix: str,
    color_map: dict[str, str] | None = None,
) -> go.Figure:
    """
    Erstellt gruppierte Balkendiagramme je Sektor (x: [year, label], y: Leistung/ Kapaz.), 
    farbcodiert nach Subcarrier.
    
    Inputs: df_sector: DataFrame eines Sektors aus prepare_multicategory
            sector: str
            years: list[int] oder []
            value_col: 'p_nom' oder 'e_nom'
            unit: 'kW' oder 'kWh'
            title_prefix: z.B. 'Nennleistungen'
            color_map: optional dict subcarrier->color
            
    Normalisiert subcarrier, baut year_str und ordnet Jahre kategorisch.
    Sortiert und baut Anzeige-Labels (display_name_map) plus Hover-Bereinigung
    Erzeugt je Subcarrier einen eigenen Bar-Trace. Links werden vorab je fachlicher
    Technologie verdichtet, damit Port-Dopplungen und überlagerte Balken vermieden werden.
    
    Outputs: go.figure (Leistungs- bzw. Kapazitätsdiagramm)
    """
    fig = go.Figure()

    if df_sector is None or df_sector.empty:
        return empty_info_figure(f"{title_prefix} ({sector})")

    df = df_sector.copy()
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce").fillna(0.0)
    df = df[df[value_col].abs() > CHART_EPS].copy()
    if df.empty:
        return empty_info_figure(
            f"{title_prefix} ({sector})",
            "Für die aktuelle Auswahl liegen keine Komponenten mit einem Wert größer 0 vor.",
        )
    df["subcarrier"] = df.get("subcarrier", DEFAULT_SUBCARRIER).fillna(DEFAULT_SUBCARRIER).astype(str)

    df["year_str"] = df["year"].astype(str)
    if years:
        years_str = [str(y) for y in years]
        df["year_str"] = pd.Categorical(df["year_str"], categories=years_str, ordered=True)

    df = df.sort_values(["year_str", "subcarrier", "label", "component"])
    name_map = display_name_map(df["label"].astype(str).unique().tolist())
    df["label_disp"] = df["label"].astype(str).map(name_map)
    df["label_disp_hover"] = df["label_disp"].astype(str).apply(strip_port_suffix_for_hover)

    sub_order = sorted(df["subcarrier"].dropna().astype(str).unique().tolist())
    fallback_colors = px.colors.qualitative.Vivid + px.colors.qualitative.Bold
    sub_colors = {}
    for idx, sc in enumerate(sub_order):
        col = color_map.get(str(sc)) if color_map is not None else None
        sub_colors[str(sc)] = col or fallback_colors[idx % len(fallback_colors)]

    single_period_view = len(df["year_str"].astype(str).unique().tolist()) <= 1
    for sc in sub_order:
        dd = df[df["subcarrier"].astype(str).eq(str(sc))].copy()
        if dd.empty:
            continue
        x_values = (
            dd["label_disp"].astype(str).tolist()
            if single_period_view
            else [dd["year_str"].astype(str).tolist(), dd["label_disp"].astype(str).tolist()]
        )
        customdata = np.column_stack([
            dd["year_str"].astype(str).values,
            dd["label_disp_hover"].astype(str).values,
            dd["subcarrier"].astype(str).values,
        ])
        fig.add_trace(go.Bar(
            name=str(sc),
            x=x_values,
            y=dd[value_col].astype(float).tolist(),
            customdata=customdata,
            marker=dict(color=sub_colors.get(str(sc), "#666666")),
            legendgroup=str(sc),
            offsetgroup=str(sc),
            alignmentgroup=str(sector),
            showlegend=True,
            hovertemplate=(
                "%{customdata[0]} - %{customdata[1]}<br>"
                "Energieträger: %{customdata[2]}<br>"
                "%{y:.2f} " + unit +
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        barmode="group",
        title=f"{title_prefix} ({sector})",
        yaxis_title=f"{title_prefix} [{unit}]",
        legend_title="Energieträger",
        margin=dict(l=30, r=30, t=60, b=150),
        showlegend=True
    )
    if single_period_view:
        fig.update_xaxes(type="category", tickangle=45)
    else:
        fig.update_xaxes(type="multicategory", tickangle=45)
    return fig


def build_expansion_path_scatter(
    by_sector: dict,
    sector: str,
    years: list,
    value_col: str = "p_nom",
    unit: str = "kW",
    max_series: int = 25,
    color_map: dict[str, str] | None = None,
) -> go.Figure:
    """
    Visualisiert den Ausbaupfad über Investitionsperioden: pro Asset eine Linie, Legende
    gruppiert nach Subcarrier
    
    Inputs: by_sector: dict[str,DataFrame] (aus prepare_multicategory)
            sector: str
            years: list[int]
            value_col: 'p_nom'
            unit: 'kW'
            max_series: int Top-N Linien nach max(value)
            color_map: optional dict subcarrier->color
            
    Filtert DataFrame nach Sektor, normalisiert Subcarrier
    Wählt Top-N Labels nach max(value_col)
    Erzeugt je label eine Scatter-Linie über inv_period; Legende zeigt Subcarrier-Gruppen
    Nutzt legend.groupclick='togglegroup' zum ein/ausblenden von Gruppen
    
    Outputs: go.figure (Scatter-Plot Ausbaupfade)
    """
    df = by_sector.get(sector)
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(title=f"Ausbaupfad ({sector}) (keine Daten)")
        return fig

    d = df.copy()
    d["subcarrier"] = d.get("subcarrier", DEFAULT_SUBCARRIER).fillna(DEFAULT_SUBCARRIER).astype(str)

    # Top-N Series
    top_labels = (
        d.groupby("label")[value_col]
         .max()
         .sort_values(ascending=False)
         .head(max_series)
         .index
    )
    d = d[d["label"].isin(top_labels)].copy()

    name_map = display_name_map(d["label"].astype(str).unique().tolist())
    d["label_disp"] = d["label"].astype(str).map(name_map)
    d["label_disp_hover"] = d["label_disp"].astype(str).apply(strip_port_suffix_for_hover)

    # X-Achse (Investitionsperioden)
    if years:
        years_str = [str(int(y)) for y in years]
        d["inv_period"] = d["year"].astype(int).astype(str)
        x_order = years_str
        title = f"Ausbaupfad ({sector})"
    else:
        d["inv_period"] = "Single"
        x_order = ["Single"]
        title = f"Ausbaupfad ({sector})"

    # Liniendiagramm: eine Linie pro label, gruppiert in der Legende nach subcarrier
    fig = go.Figure()

    shown_in_legend = set()

    # Sortieren nach Perioden
    if years:
        d["_year_sort"] = d["inv_period"].astype(int)
        d = d.sort_values(["_year_sort", "subcarrier", "label", "component"])
    else:
        d = d.sort_values(["subcarrier", "label", "component"])

    for label, g in d.groupby("label", sort=False):
        g2 = g.copy()

        sc = str(g2["subcarrier"].iloc[0])
        label_disp_hover = str(g2["label_disp_hover"].iloc[0])

        # Reihenfolge entlang der X-Achse
        if years:
            g2 = g2.sort_values("_year_sort")

        x = g2["inv_period"].astype(str).tolist()
        y = g2[value_col].astype(float).tolist()

        showlegend = sc not in shown_in_legend
        if showlegend:
            shown_in_legend.add(sc)

        col = (color_map.get(sc) if (color_map is not None) else None)

        # customdata für Hover
        customdata = np.column_stack([
            np.full(len(g2), label_disp_hover),
            np.full(len(g2), sc),
        ])
        # ... innerhalb: for label, g in d.groupby("label", sort=False):

        x = g2["inv_period"].astype(str).tolist()
        y = g2[value_col].astype(float).tolist()

        # nur am letzten Punkt beschriften
        txt = [""] * len(x)
        if len(txt) > 0:
            txt[0] = label_disp_hover   # das ist der "Komponentenname" ohne _p/_e

        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode="lines+markers+text",
            text=txt,
            textposition="middle left",
            cliponaxis=False,
            legendgroup=sc,
            showlegend=showlegend,
            name=sc,
            line=dict(color=col) if col else None,
            marker=dict(size=15, color=col) if col else dict(size=15),
            customdata=customdata,
            hovertemplate=(
                "%{x} - %{customdata[0]}<br>"
                "Energieträger: %{customdata[1]}<br>"
                "%{y:.2f} " + unit +
                "<extra></extra>"
            ),
        ))

    fig.update_xaxes(range=[-1, len(x_order)-0.5])

    fig.update_layout(
        title=title,
        legend_title="Energieträger",
        margin=dict(l=30, r=30, t=60, b=50),
        legend=dict(groupclick="togglegroup"),
    )
    fig.update_xaxes(
        title="Investitionsperiode",
        type="category",
        categoryorder="array",
        categoryarray=x_order,
    )
    fig.update_yaxes(title=f"Leistung [{unit}]")

    return fig


# Links zur Anbindung von Stores flaggen, damit sie nicht im Lifetime-Diagramm angezeigt werden

def link_is_store_connection_topology(row: pd.Series, store_buses: set[str], max_i: int = 9) -> bool:
    """
    Erkennt Links, die topologisch an interne Store-Busse angeschlossen sind 
    (um sie aus Lifetime-Plots auszublenden)
    
    Inputs: row: pd.Series (Link-Zeile)
            store_buses: set[str]
            max_i: int (Default 9)
            
    Iteriert über bus0..bus{max_i}
    Wenn irgendein bus{i} in store_buses liegt: True
    
    Outputs: bool
    """
    if not store_buses:
        return False
    for i in range(0, max_i + 1):
        b = row.get(f"bus{i}", None)
        if b is None or pd.isna(b):
            continue
        b = str(b).strip()
        if b and b in store_buses:
            return True
    return False


def build_lifetime_table(n: pypsa.Network) -> pd.DataFrame:
    """
    Erstellt eine Tabelle mit Aktivitätszeiträumen (build_year, end_year) und Lifetime-Flags je
    Komponente; inkl. Ausschlussflag für Store-Anbindungslinks
    
    Inputs: n:pypsa.Network
    
    Ermittelt Investitionshorizont (MIP: min/max(years), sonst aus snapshots)
    Erkennt interne Store-Busse (infer_internal_store_buses)
    Iteriert über generators, stores, storage_units, links, lines (wenn vorhanden)
    Leitet Kapazität aus p_nom/s_nom/e_nom ab und ignoriert sehr kleine Werte (EPS)
    Normalisiert build_year; berechnet end_year aus lifetime (oder setzt display_end)
    Setzt Flags: lifetime_missing, lifetime_infinite und exclude_from_lifetime_plot (bei
    Store-Link)
    Ermittelt sector/subcarrier je Komponente 
    (Links: primärer Output-Bus; Sonderfall "variabel")
    
    Outputs: DataFrame: lifetime-Tabelle mit build_year/end_year und Metadaten
    """
    years = get_investment_years(n)
    years_set = set(years)

    EPS = 1e-6

    # Topologische Store-Bus-Menge (robust gegen Namenskonventionen)
    internal_store_buses = infer_internal_store_buses(n)
    bhkw_parent_caps = _bhkw_parent_capacity_by_build(n)

    def capacity_from_row(component: str, r: pd.Series) -> tuple[float, str]:
        if component == "stores":
            for col in ("e_nom_opt", "e_nom"):
                if col in r.index and pd.notna(r.get(col)):
                    try:
                        return float(r.get(col)), "kWh"
                    except Exception:
                        pass
            return 0.0, "kWh"

        for col in ("p_nom_opt", "p_nom", "s_nom_opt", "s_nom"):
            if col in r.index and pd.notna(r.get(col)):
                try:
                    return float(r.get(col)), "kW"
                except Exception:
                    pass
        return 0.0, "kW"

    if years:
        horizon_start = int(min(years))
        last_period = int(max(years))
    else:
        try:
            snap_year_min = int(pd.to_datetime(pd.Index(n.snapshots)).min().year)
            snap_year_max = int(pd.to_datetime(pd.Index(n.snapshots)).max().year)
            horizon_start = snap_year_min
            last_period = snap_year_max
        except Exception:
            horizon_start = int(pd.Timestamp.today().year)
            last_period = horizon_start

    def norm_build_year(by):
        if by is None or pd.isna(by):
            return horizon_start
        try:
            by_f = float(by)
        except Exception:
            return horizon_start
        if not np.isfinite(by_f):
            return horizon_start
        y = int(by_f)
        if y < 1900:
            return horizon_start
        return y

    def _iter_component_tables():
        tables = []
        if hasattr(n, "generators") and not n.generators.empty:
            tables.append(("generators", n.generators))
        if hasattr(n, "stores") and not n.stores.empty:
            tables.append(("stores", n.stores))
        if hasattr(n, "storage_units") and not n.storage_units.empty:
            tables.append(("storage_units", n.storage_units))
        if hasattr(n, "links") and not n.links.empty:
            tables.append(("links", n.links))
        if hasattr(n, "lines") and not n.lines.empty:
            tables.append(("lines", n.lines))
        return tables

    finite_lifetimes_active = []
    finite_lifetimes_all = []

    for comp_name, df in _iter_component_tables():
        if "lifetime" not in df.columns:
            continue
        for _, r in df.iterrows():
            name = str(r.name)
            if comp_name == "links" and _is_inactive_bhkw_auxiliary(name, bhkw_parent_caps):
                continue
            cap, _unit = capacity_from_row(comp_name, r)
            if cap <= EPS:
                continue
            lt = r.get("lifetime", None)
            if lt is None or pd.isna(lt):
                continue
            try:
                lt_f = float(lt)
            except Exception:
                continue
            if not np.isfinite(lt_f):
                continue

            start = norm_build_year(r.get("build_year", None))
            end = start + lt_f

            finite_lifetimes_all.append(lt_f)
            if start <= last_period < end:
                finite_lifetimes_active.append(lt_f)

    if finite_lifetimes_active:
        max_life_active = float(max(finite_lifetimes_active))
    elif finite_lifetimes_all:
        max_life_active = float(max(finite_lifetimes_all))
    else:
        max_life_active = 1.0

    display_end = int(last_period + max_life_active)

    rows = []

    def _link_primary_output_bus(row: pd.Series):
        for i in range(1, 10):
            b = row.get(f"bus{i}", None)
            if b is not None and not pd.isna(b) and str(b).strip() != "":
                return b
        b0 = row.get("bus0", None)
        if b0 is not None and not pd.isna(b0) and str(b0).strip() != "":
            return b0
        return None

    def _line_sector_bus(row: pd.Series):
        b0 = row.get("bus0", None)
        if b0 is not None and not pd.isna(b0) and str(b0).strip() != "":
            return b0
        b1 = row.get("bus1", None)
        if b1 is not None and not pd.isna(b1) and str(b1).strip() != "":
            return b1
        return None

    def add_rows(df: pd.DataFrame, component: str):
        if df is None or df.empty:
            return

        has_by = "build_year" in df.columns
        has_lt = "lifetime" in df.columns

        for name, r in df.iterrows():
            if component == "links" and _is_inactive_bhkw_auxiliary(str(name), bhkw_parent_caps):
                continue
            cap, cap_unit = capacity_from_row(component, r)
            if cap <= EPS:
                continue

            start = norm_build_year(r.get("build_year", None)) if has_by else horizon_start

            lt = r.get("lifetime", None) if has_lt else None
            lifetime_missing = (lt is None) or (pd.isna(lt)) or (not has_lt)

            lifetime_infinite = False
            lifetime_val = None

            if lifetime_missing:
                end = display_end
            else:
                try:
                    lt_f = float(lt)
                except Exception:
                    lt_f = np.nan

                if not np.isfinite(lt_f):
                    lifetime_infinite = True
                    lifetime_val = np.inf
                    end = display_end
                else:
                    lifetime_val = lt_f
                    end = int(start + lt_f)

            if end < start:
                end = start

            base, _ = split_base_and_year(str(name), years_set)

            if component in ("generators", "stores", "storage_units"):
                sec, sc = sector_subcarrier_from_component_row(n, component, r)
            elif component == "lines":
                bus = _line_sector_bus(r)
                sec, sc = sector_subcarrier_from_bus(n, bus)
            elif component == "links":
                bus_out = _link_primary_output_bus(r)
                sec, sc = sector_subcarrier_from_bus(n, bus_out)
                sec, sc = _display_sector_subcarrier_for_power_row(component, str(name), sec, sc)
                is_store_link = link_is_store_connection_topology(r, internal_store_buses, max_i=9)
            
                if str(sc).strip().lower() == "variabel":
                    bus0 = r.get("bus0", None)
                    if bus0 is not None and not pd.isna(bus0) and str(bus0).strip() != "" and str(bus0) in n.buses.index:
                        raw_bus0_car = n.buses.at[str(bus0), "carrier"] if "carrier" in n.buses.columns else pd.NA
                        car0, _sub0 = split_carrier_subcarrier(raw_bus0_car)
                        sc = car0 if car0 else DEFAULT_SUBCARRIER
                    else:
                        sc = DEFAULT_SUBCARRIER
            else:
                sec, sc = ("Sonstige", DEFAULT_SUBCARRIER)

            sc = DEFAULT_SUBCARRIER if (sc is None or pd.isna(sc) or str(sc).strip() == "") else str(sc)

            rows.append({
                "sector": sec,
                "subcarrier": sc,
                "component": component,
                "name": str(name),
                "base_name": base,
                "build_year": int(start),
                "end_year": int(end),
                "lifetime": lifetime_val,
                "lifetime_infinite": lifetime_infinite,
                "lifetime_missing": lifetime_missing,
                "capacity": float(cap),
                "capacity_unit": cap_unit,
                "exclude_from_lifetime_plot": bool(is_store_link) if component == "links" else False,
            })

    add_rows(n.generators if hasattr(n, "generators") else None, "generators")
    add_rows(n.stores if hasattr(n, "stores") else None, "stores")
    add_rows(n.storage_units if hasattr(n, "storage_units") else None, "storage_units")
    add_rows(n.lines if hasattr(n, "lines") else None, "lines")
    add_rows(n.links if hasattr(n, "links") else None, "links")

    return pd.DataFrame(rows)


def build_lifetime_timeline_fig(
        df_life: pd.DataFrame, 
        sector: str, 
        color_map: dict[str, str] | None = None
        ) -> go.Figure:
    """
    Erstellt ein Timeline-Diagramm (px.timeline) der Aktivitätszeiträume je Komponente in
    einem Sektor, farbcodiert nach Subcarrier

    Inputs: df_life: DataFrame aus build_lifetime_table
            sector: str
            color_map: optional dict subcarrier->color
            
    Filtert auf Sektor, blendet exclude_from_lifetime_plot aus
    Erzeugt Hover-Felder: comp_name_disp (ohne Prefix/Suffix), lifetime_disp ('unbekannt',
    'durchgehend vorhanden', oder Zahl).                                        
    Konvertiert build_year/end_year in Datumswerte (01-01)
    Erzeugt px.timeline und setzt Hovertemplate
    Konfiguriert Achsen (Jahrestakt) und Layout
    
    Outputs: go.figure (Lifetime-Gantt-Chart)
    """
    
    if df_life is None or df_life.empty:
        return go.Figure().update_layout(title=f"Lebensdauer - {sector} (keine Daten)")

    d = df_life[df_life["sector"] == sector].copy()
    
    # Store-Anbindungslinks im Lifetime-Diagramm ausblenden
    if "exclude_from_lifetime_plot" in d.columns:
        d = d[~((d["component"].astype(str) == "links") & (d["exclude_from_lifetime_plot"].astype(bool)))]
        
    if d.empty:
        return go.Figure().update_layout(title=f"Lebensdauer - {sector} (keine Daten)")

    d["subcarrier"] = d.get("subcarrier", DEFAULT_SUBCARRIER).fillna(DEFAULT_SUBCARRIER).astype(str)
    d = d.sort_values(["build_year", "subcarrier", "component", "name"], ascending=[True, True, True, True])
    

    # --- Schöner Komponentenname (ohne _YYYY etc.), nur für Hover ---
    if "base_name" in d.columns:
        d["comp_name_disp"] = d["base_name"].astype(str).map(strip_prefix).map(strip_variable_suffix)
    else:
        d["comp_name_disp"] = d["name"].astype(str).map(strip_prefix).map(strip_variable_suffix)

    # --- Lebensdauer als String für Hover ---
    # Reihenfolge: missing -> "unbekannt", infinite -> "∞", sonst Zahl
    lt = pd.to_numeric(d.get("lifetime", pd.Series(index=d.index, dtype=float)), errors="coerce")
    d["lifetime_disp"] = np.where(
        d.get("lifetime_missing", False).astype(bool),
        "unbekannt",
        np.where(
            d.get("lifetime_infinite", False).astype(bool),
            "durchgehend vorhanden",
            lt.round(2).astype(str)
        )
    )

    d["start_dt"] = pd.to_datetime(d["build_year"].astype(int).astype(str) + "-01-01", errors="coerce")
    d["end_dt"]   = pd.to_datetime(d["end_year"].astype(int).astype(str) + "-01-01", errors="coerce")
    d = d.dropna(subset=["start_dt", "end_dt"])
    if d.empty:
        return go.Figure().update_layout(title=f"Lebensdauer - {sector} (keine gültigen Jahre)")

    fig = px.timeline(
        d,
        x_start="start_dt",
        x_end="end_dt",
        y="name",
        color="subcarrier",
        color_discrete_map=color_map if color_map is not None else None,
        custom_data=["comp_name_disp", "lifetime_disp", "build_year", "end_year"],
        title=f"Lebensdauer / Aktivitätszeitraum - {sector}",
    )

    # Hovertext bündelt Aktivitätszeitraum, Baujahr und Lebensdauer.
    fig.update_traces(
        hovertemplate=(
            "%{customdata[0]}<br>"
            "Lebensdauer (Jahre): %{customdata[1]}<br>"
            "Baujahr: %{customdata[2]}<br>"
            "Endjahr: %{customdata[3]}"
            "<extra></extra>"
        )
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(tickformat="%Y", dtick="M12", title="Jahr")
    fig.update_yaxes(title="Komponente")
    fig.update_layout(margin=dict(l=30, r=30, t=60, b=50), height=650, legend_title="Energieträger")
    return fig

#%% Active-Assets pro Investitionsperiode (Timeseries-Filter)

def active_assets_in_period(df_life: pd.DataFrame, period_value) -> set[tuple[str, str]]:
    """
    Bestimmt die Menge aktiver Assets (component, name) für eine Investitionsperiode anhand
    df_life
    
    Inputs: df_life: DataFrame
            period_value: z.B. '2030'
            
    Konvertiert period_value nach int
    Filtert df_life auf build_year <= p < end_year
    Gibt Set aus (component, name) zurück

    Outputs: set[tuple[str,str]]
    """
    if df_life is None or df_life.empty:
        return set()
    try:
        p = int(period_value)
    except Exception:
        return set()

    d = df_life.copy().dropna(subset=["build_year", "end_year"])
    active = d[(d["build_year"].astype(int) <= p) & (p < d["end_year"].astype(int))]
    return set(zip(active["component"].astype(str), active["name"].astype(str)))


def filter_meta_to_active(
        meta: pd.DataFrame, 
        active_set: set[tuple[str, str]], 
        df_life: pd.DataFrame) -> pd.DataFrame:
    """
    Filtert die Zeitreihen-Metadaten (meta) auf Assets, die in einer Periode aktiv sind;
    Komponenten ohne Lifetime-Info bleiben erhalten.
    
    Inputs: meta: Meta-DataFrame (Index=Spalte)
            active_set: set[(component, asset)]
            df_life: Lifetime-DataFrame
            
    Ermittelt Komponenten, die überhaupt Lifetime-Informationen haben.
    Behält Meta-Zeilen, wenn Komponente keine Lifetime führt oder (comp, asset) 
    in active_set enthalten ist
    
    Outputs: DataFrame: gefilterter Meta-df
    """
    if meta is None or meta.empty or df_life is None or df_life.empty:
        return meta
    comps_with_life = set(df_life["component"].astype(str).unique())

    keep_mask = []
    for _, r in meta.iterrows():
        comp = str(r.get("component", ""))
        asset = str(r.get("asset", ""))
        if comp not in comps_with_life:
            keep_mask.append(True)
            continue
        keep_mask.append((comp, asset) in active_set)
    return meta.loc[keep_mask].copy()


#%% Speicherkapazität (kWh) Tabelle

def energy_nominal_from_store(df_static: pd.DataFrame) -> pd.Series:
    """
    Liest für Stores die Energiespeicherkapazität (e_nom_opt/e_nom) als Series aus
    
    Inputs: df_static: DataFrame (nur Stores werden verarbeitet)
    
    Sucht e_nom_opt, dann e_nom, sonst leere float-Serie
    
    Outputs: pd.Series    
    """
    for col in ("e_nom_opt", "e_nom"):
        if col in df_static.columns:
            return df_static[col]
    return pd.Series(index=df_static.index, dtype=float)


def build_energy_capacity_table(n: pypsa.Network) -> pd.DataFrame:
    """
    Erstellt eine tabellarische Übersicht der Speicherkapazitäten (kWh) für Stores und Storage
    Units (über p_nom*max_hours)
    
    Inputs: N: pypsa.Network
    
    Ermittelt years/years_set
    Stores: e_nom aus energy_nominal_from_store; Name -> (base, year); Sektor/Subcarrier per
    sector_subcarrier_from_component_row
    Storage Units: e_nom = p_nom * max_hours; analoges Mapping
    Erzeugt DataFrame mit Spalten: sector, subcarrier, component, name, base_name, year,
    port="e", e_nom
    
    Outputs: DataFrame: Speicherkapazitäten [kWh]
    """
    cols = ["sector", "subcarrier", "component", "name", "base_name", "year", "port", "e_nom"]
    years = get_investment_years(n)
    years_set = set(years)
    rows = []

    if hasattr(n, "stores") and not n.stores.empty:
        df = n.stores
        e_nom = energy_nominal_from_store(df).fillna(0.0)
        for name, r in df.iterrows():
            base, year = split_base_and_year(name, years_set)
            s, sc = sector_subcarrier_from_component_row(n, "stores", r)
            rows.append({
                "sector": s, "subcarrier": sc, "component": "stores",
                "name": str(name), "base_name": base, "year": year,
                "port": "e", "e_nom": float(e_nom.get(name, 0.0)),
            })

    if hasattr(n, "storage_units") and not n.storage_units.empty:
        df = n.storage_units
        p_nom = nominal_from_static(df).fillna(0.0)
        max_hours = df["max_hours"] if "max_hours" in df.columns else pd.Series(0.0, index=df.index)
        max_hours = max_hours.fillna(0.0).astype(float)
        e_nom = (p_nom.astype(float) * max_hours)

        for name, r in df.iterrows():
            base, year = split_base_and_year(name, years_set)
            s, sc = sector_subcarrier_from_component_row(n, "storage_units", r)
            rows.append({
                "sector": s, "subcarrier": sc, "component": "storage_units",
                "name": str(name), "base_name": base, "year": year,
                "port": "e", "e_nom": float(e_nom.get(name, 0.0)),
            })

    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        return out
    out["e_nom"] = out["e_nom"].fillna(0.0)
    out["subcarrier"] = out.get("subcarrier", DEFAULT_SUBCARRIER).fillna(DEFAULT_SUBCARRIER)
    return out


#%% Wirtschaftlichkeit (Kosten)

COST_UNIT = "EUR/Jahr"
CURRENCY_LABEL = "EUR"
MARGINAL_COST_IS_EUR_PER_MWH = False
COST_COMPONENTS = ["generators", "links", "storage_units", "stores", "lines",]
DEFAULT_DISCOUNT_RATE = 0.0  # r=0 => Overnight = Annuität * Lifetime
# Verhindert das doppelte zählen der CO2-Kosten in OPEX und einzeln
CO2_COSTS_ALREADY_INCLUDED_IN_OPEX = True


def _co2_costs_already_in_opex_from_network(n: pypsa.Network | None) -> bool:
    """
    Liest aus der PyPSA-Datei, ob CO2-Kosten schon in marginal_cost enthalten sind.

    Inputs: PyPSA-Netzwerk oder None.
    Outputs: Hinweis zur CO2-Kostenbehandlung.
    """
    if n is None:
        return CO2_COSTS_ALREADY_INCLUDED_IN_OPEX
    meta = getattr(n, "meta", None)
    if isinstance(meta, pd.Series):
        meta = meta.to_dict()
    if isinstance(meta, str):
        parsed_meta = None
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed_meta = parser(meta)
                break
            except Exception:
                continue
        meta = parsed_meta if parsed_meta is not None else meta
    if isinstance(meta, dict):
        for key in ("co2_costs_in_marginal_cost", "co2_costs_already_in_opex"):
            if key in meta:
                value = meta.get(key)
                if isinstance(value, str):
                    return value.strip().lower() in {"1", "true", "yes", "ja", "y"}
                return bool(value)
    return CO2_COSTS_ALREADY_INCLUDED_IN_OPEX


def _co2_costs_already_in_opex_from_df(df: pd.DataFrame | None) -> bool:
    """
    Liest aus dem DataFrame, ob CO2-Kosten schon in marginal_cost enthalten sind.
    
    Inputs: DataFrame
    Outputs: True oder False für CO2-Kosten in OPEX.
    """
    if df is not None and hasattr(df, "attrs") and "co2_costs_already_in_opex" in df.attrs:
        return bool(df.attrs.get("co2_costs_already_in_opex"))
    return CO2_COSTS_ALREADY_INCLUDED_IN_OPEX


def _get_objective_snapshot_weights(n: pypsa.Network) -> pd.Series:
    """
    Liest Snapshot-Gewichtungen für die Zielfunktion ('objective') robust aus
    n.snapshot_weightings
    
    Inputs: n: pypsa.Network
    
    Falls snapshot_weightings fehlt: Series(1.0)
    Falls DataFrame mit Spalte 'objective': nutzt diese Spalte
    Falls Attribut 'objective' vorhanden: nutzt sw.objective
    Sonst Fallback: Series(1.0)
    
    Outputs: pd.Series: Weightings je Snapshot
    """
    sw = getattr(n, "snapshot_weightings", None)
    if sw is None:
        return pd.Series(1.0, index=n.snapshots, name="objective")
    if isinstance(sw, pd.DataFrame) and "objective" in sw.columns:
        return sw["objective"]
    if hasattr(sw, "objective"):
        return sw.objective
    return pd.Series(1.0, index=n.snapshots, name="objective")


def _nominal_opt_series(comp_name: str, df: pd.DataFrame) -> pd.Series:
    """
    Liest die optimierte Nennleistung/ -kapazität je Komponente (p_nom_opt / e_nom_opt etc.) als
    numerische Series

    Inputs: comp_name: str
            df: DataFrame (static)
            
    Stores: e_nom_opt/e_nom
    Sonst: p_nom_opt/p_nom/s_nom_opt/s_nom
    Fallback: 0.0-Series
    
    Outputs: pd.Series
    """
    if comp_name == "stores":
        for col in ("e_nom_opt", "e_nom"):
            if col in df.columns:
                return pd.to_numeric(df[col], errors="coerce")
        return pd.Series(0.0, index=df.index)
    for col in ("p_nom_opt", "p_nom", "s_nom_opt", "s_nom"):
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(0.0, index=df.index)


def _safe_cost_series(df: pd.DataFrame, col: str) -> pd.Series:
    """
    Gibt eine numerische Kostenseries aus df[col] zurück
    Fehlt die Spalte, wird 0.0 zurückgegeben
    
    Inputs: df: DataFrame
            col: str
    
    Outputs: pd.Series
    """
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=df.index)


def _infer_build_year(name: str, df: pd.DataFrame, years: list[int]) -> int | None:
    """
    Leitet ein build_year für ein Asset ab, bevorzugt aus Namenssuffix '_YYYY', sonst aus Spalte
    build_year, sonst aus min(years)
    
    Inputs: name: str
            df: DataFrame.
            years: list[int]
            
    Prüft Suffix via split_base_and_year
    Sonst: versucht df.at[name,'build_year'] zu lesen
    Fallback: min(years) oder None
    
    Outputs: int | None
    """
    years_set = set(years)
    _base, y_suffix = split_base_and_year(name, years_set)
    if y_suffix is not None:
        return int(y_suffix)
    if "build_year" in df.columns:
        by = df.at[name, "build_year"]
        if by is not None and not pd.isna(by):
            try:
                return int(float(by))
            except Exception:
                pass
    if years:
        return int(min(years))
    return None


def _infer_end_year(name: str, df: pd.DataFrame, build_year: int | None) -> float:
    """
    Berechnet end_year aus build_year + lifetime; ohne lifetime oder fehlendem build_year -> inf
    
    Inputs: name: str
            df: DataFrame
            build_year: int|None
            
    Wenn build_year None: inf
    Wenn 'lifetime' fehlt/ungültig: inf
    Sonst: build_year + lifetime
    
    Outputs: float: end_year (kann inf sein)
    """    
    if build_year is None:
        return np.inf
    if "lifetime" not in df.columns:
        return np.inf
    lt = df.at[name, "lifetime"]
    if lt is None or pd.isna(lt):
        return np.inf
    try:
        lt_f = float(lt)
    except Exception:
        return np.inf
    if not np.isfinite(lt_f):
        return np.inf
    return float(build_year) + lt_f


def _map_build_to_investment_period(build_year: int, years: list[int]) -> int:
    """
    Mappt ein build_year auf die nächste (>=) Investitionsperiode in years.
    
    Inputs: build_year: int
            years: list[int]
    
    Wenn build_year exakt in years: identisch
    Sonst: wählt kleinste Periode >= build_year, sonst letzte Periode
    
    Outputs: int: Investitionsperiode
    """
    if not years:
        raise ValueError("years leer, obwohl MIP erwartet wurde.")
    if build_year in years:
        return build_year
    future = [y for y in years if y >= build_year]
    return future[0] if future else years[-1]

def _annuity_factor(r: float, n_years: float) -> float:
    """
    Berechnet den Annuitätsfaktor a(r,n) zur Annualisierung von Overnight-Kosten.
    
    Inputs: r: float (discount rate)
            n_years: float (lifetime)
            
    Validiert Endlichkeit und n_years>0
    Sonderfall r·0: 1/n_years
    Sonst: r / (1 - (1+r)^(-n))
    
    Outputs: float (oder NaN bei ungültigen Eingaben)
    """
    try:
        r = float(r)
        n_years = float(n_years)
    except Exception:
        return np.nan
    if (not np.isfinite(r)) or (not np.isfinite(n_years)) or n_years <= 0:
        return np.nan
    if abs(r) < 1e-12:
        return 1.0 / n_years
    return r / (1.0 - (1.0 + r) ** (-n_years))


def _overnight_from_annualized(annualized: float, r: float, lifetime: float) -> float:
    """
    Rekonstruiert Overnight-Kosten aus annualisierten Kosten via Division durch
    Annuitätsfaktor
    
    Inputs: annualized: float
            r: float
            lifetime: float
    
    Berechnet a = _annuity_factor(r,lifetime)
    Wenn a ungültig: gibt annualized zurück
    Sonst: annualized/a
    
    Outputs: float: overnight
    """
    try:
        annualized = float(annualized)
    except Exception:
        return 0.0
    a = _annuity_factor(r, lifetime)
    if (a is None) or (not np.isfinite(a)) or a <= 0:
        return annualized
    return annualized / a


def _infer_build_year_strict(name: str, df: pd.DataFrame, years: list[int]) -> int | None:
    """
    Strenge Neubau-Erkennung: zählt nur, wenn ein eindeutiges Build-Jahr existiert (Suffix oder
    build_year-Spalte)
    
    Inputs: name: str
            df: DataFrame
            years: list[int]
            
    Prüft Suffix _YYYY in years
    Sonst: liest build_year, wenn vorhanden und konvertierbar
    Sonst None
    
    Outputs: int|None
    """
    years_set = set(years)
    _base, y_suffix = split_base_and_year(str(name), years_set)
    if y_suffix is not None:
        return int(y_suffix)

    if "build_year" in df.columns:
        by = df.at[name, "build_year"]
        if by is not None and not pd.isna(by):
            try:
                return int(float(by))
            except Exception:
                pass
    return None


def build_investment_capex_df(n: pypsa.Network) -> pd.DataFrame:
    """
    Erzeugt eine Tabelle nicht-annualisierter Investitionen je Investitionsperiode (Overnight
    CAPEX) für neu gebaute Assets
    
    Inputs: n: pypsa.Network
    
    Ermittelt Investitionsperioden years
    Iteriert über COST_COMPONENTS und deren statische Tabellen
    Für jedes Asset: nimmt nominelle Kapazität nom_i
    Wenn MIP: nur Neubau-Assets via _infer_build_year_strict; bestimmt build_period
    Bestimmt unit_cost: entweder explizit 'capital_cost_overnight' oder rekonstruiert overnight
    aus annualisiertem capital_cost via discount_rate und lifetime
    Überspringt Assets ohne gültige lifetime (um Fehlinterpretationen zu vermeiden)
    Berechnet investment_capex = unit_cost * nom_i; sammelt Zeilen (period, component,
    name, base_name, investment_capex)
    
    Outputs: DataFrame: Investitions-CAPEX je Asset und Periode
    """
    years = get_investment_years(n)
    years_set = set(years)

    rows = []

    for comp_name in COST_COMPONENTS:
        if not hasattr(n, comp_name):
            continue
        static_df = getattr(n, comp_name)
        if static_df is None or static_df.empty:
            continue

        nom = _nominal_opt_series(comp_name, static_df).fillna(0.0).astype(float)
        cap_cost_annual = _safe_cost_series(static_df, "capital_cost")  # typischerweise €/unit/a

        # falls irgendwann explizite Overnight-Kosten im Datensatz vorliegen
        cap_cost_overnight = None
        if "capital_cost_overnight" in static_df.columns:
            cap_cost_overnight = pd.to_numeric(static_df["capital_cost_overnight"], errors="coerce").fillna(0.0)

        for name in static_df.index:
            nom_i = float(nom.get(name, 0.0))
            if nom_i <= 0.0:
                continue

            if years:
                by = _infer_build_year_strict(str(name), static_df, years)
                if by is None:
                    continue  # kein eindeutig neuer Build -> nicht zählen
                build_period = _map_build_to_investment_period(int(by), years)
                period_label = str(build_period)
            else:
                period_label = "Single"

            if cap_cost_overnight is not None:
                unit_cost = float(cap_cost_overnight.get(name, 0.0))
            else:
                ann = float(cap_cost_annual.get(name, 0.0))

           # Default: r=0, wenn nicht explizit vorhanden
                r = DEFAULT_DISCOUNT_RATE
                if "discount_rate" in static_df.columns:
                    v = static_df.at[name, "discount_rate"]
                    if v is not None and not pd.isna(v):
                        try:
                            r = float(v)
                        except Exception:
                            r = DEFAULT_DISCOUNT_RATE

          # Lifetime ist Pflicht, sonst keine De-Annualisierung möglich
                lt = np.nan
                if "lifetime" in static_df.columns:
                    v = static_df.at[name, "lifetime"]
                    if v is not None and not pd.isna(v):
                       try:
                           lt = float(v)
                       except Exception:
                           lt = np.nan

    # Wenn lifetime fehlt/ungültig: überspringen (sonst würden Annuitäten als Overnight fehlinterpretiert)
                if (not np.isfinite(lt)) or (lt <= 0):
                     continue

                unit_cost = _overnight_from_annualized(ann, r, lt)

            inv = unit_cost * nom_i
            if (not np.isfinite(inv)) or abs(inv) <= 0.0:
                continue

            base_name, _ = split_base_and_year(str(name), years_set)
            rows.append({
                "period": period_label,
                "component": comp_name,
                "name": str(name),
                "base_name": base_name,
                "investment_capex": float(inv),
            })

    return pd.DataFrame(rows)


def _get_dispatch_df(n: pypsa.Network, comp_name: str) -> pd.DataFrame | None:
    """
    Liefert ein geeignetes Dispatch-DataFrame (p) für eine Komponente aus
    n.components.dynamic
    
    Inputs: n:pypsa.Network
            comp_name: str
    
    Für links: bevorzugt p0, sonst kleinster vorhandener p{i}
    Für lines: p0, sonst p1
    Für andere: p, sonst None

    Outputs: DataFrame|None
    """
    if not hasattr(n, "components") or not hasattr(n.components, comp_name):
        return None
    dyn = getattr(n.components, comp_name).dynamic

    if comp_name == "links":
        if "p0" in dyn:
            return dyn.get("p0")
        port_attrs = [a for a in dyn.keys() if re.match(r"^p\d+$", str(a))]
        if port_attrs:
            port_attrs = sorted(port_attrs, key=lambda s: int(str(s)[1:]))
            return dyn.get(port_attrs[0])
        return None

    if comp_name == "lines":
        if "p0" in dyn:
            return dyn.get("p0")
        if "p1" in dyn:
            return dyn.get("p1")
        return None

    if "p" in dyn:
        return dyn.get("p")
    return None

def _variable_opex_by_period(
    n: pypsa.Network,
    comp_name: str,
    static_df: pd.DataFrame,
    years: list[int],
    weights: pd.Series,
) -> pd.DataFrame:
    """
    Berechnet variable OPEX je Periode aus Dispatch * marginal_cost * Snapshot-Weightings
    
    Inputs: n: pypsa.Network
            comp_name: str
            static_df: DataFrame (statisch, enthält marginal_cost)
            years: list[int]
            weights: pd.Series (Snapshot-Weights)
            
    Lädt Dispatch p_df via _get_dispatch_df; falls None: gibt Null-DF zurück
    Passt marginal_cost auf Dispatch-Spalten an; Passt weights auf Index an
    Berechnet Energie = |p| * w
    Optional: Umrechnung kWh->MWh, wenn MARGINAL_COST_IS_EUR_PER_MWH True
    Kostenzeitreihe = Energie * marginal_cost
    MIP: gruppiert nach period-level (level=0); sonst summiert zu 'Single'

    Outputs: DataFrame: index=Perioden, columns=Assets, values=variable OPEX
    """
    p_df = _get_dispatch_df(n, comp_name)
    if p_df is None or p_df.empty:
        idx = [str(y) for y in years] if years else ["Single"]
        return pd.DataFrame(0.0, index=idx, columns=static_df.index)

    mc = _safe_cost_series(static_df, "marginal_cost").reindex(p_df.columns).fillna(0.0)
    w = weights.reindex(p_df.index).fillna(0.0)

    energy = p_df.abs().mul(w, axis=0)
    if MARGINAL_COST_IS_EUR_PER_MWH:
        energy = energy / 1000.0

    cost_ts = energy.mul(mc, axis=1)

    if isinstance(cost_ts.index, pd.MultiIndex):
        out = cost_ts.groupby(level=0).sum()
        out.index = out.index.astype(str)
        return out

    out = pd.DataFrame(cost_ts.sum(), columns=["Single"]).T
    out.index = ["Single"]
    return out


def _remove_duplicate_fuel_link_opex(
    n: pypsa.Network,
    comp_name: str,
    static_df: pd.DataFrame,
    var_opex: pd.DataFrame,
) -> pd.DataFrame:
    """
    Verhindert die Doppelzählung von Brennstoffkosten in OPEX. 
    Z.B. durch Doppelzählung bei Gasnetzbezug -> Gas -> BHKW -> Strom -> Wärmepumpe
    
    Inputs: n, comp_name, static_df, var_opex.
    Outputs: DataFrame mit bereinigten variablen OPEX.
    """
    if comp_name != "links" or var_opex is None or var_opex.empty:
        return var_opex
    if static_df is None or static_df.empty or not hasattr(n, "generators") or n.generators is None:
        return var_opex

    out = var_opex.copy()
    gen_df = n.generators
    for name, row in static_df.iterrows():
        if name not in out.columns:
            continue
        marginal_cost = row.get("marginal_cost", 0.0)
        try:
            marginal_cost = float(marginal_cost)
        except Exception:
            marginal_cost = 0.0
        if abs(marginal_cost) <= 1e-12:
            continue

        bus0 = str(row.get("bus0", "") or "")
        context = f"{name} {bus0} {row.get('carrier', '')}".lower()
        fuel_like = any(token in context for token in ("gas", "wasserstoff", "hydrogen", "h2", "benzin", "diesel", "oel", "öl", "kohle", "coal"))
        if not fuel_like or "bus" not in gen_df.columns:
            continue

        supply = gen_df[gen_df["bus"].astype(str) == bus0].copy()
        if supply.empty:
            continue
        supply_names = " ".join(supply.index.astype(str).tolist()).lower()
        supply_mc = (
            pd.to_numeric(supply["marginal_cost"], errors="coerce").fillna(0.0).abs().sum()
            if "marginal_cost" in supply.columns
            else 0.0
        )
        if "bezug" in supply_names and float(supply_mc) > 1e-12:
            out[name] = 0.0
    return out


def build_investment_capex_totals_fig(
    df_inv: pd.DataFrame,
    years: list[int],
    horizon_end_year: int | None = None,
) -> go.Figure:
    """
    Erstellt ein Säulendiagramm der Gesamtinvestitionen (Overnight CAPEX) je Periode;
    Single-year als einzelner Balken 'CAPEX (Summe)'
    
    Inputs: df_inv: DataFrame aus build_investment_capex_df
            years: list[int]
            
    Aggregiert df_inv nach 'period' und summiert investment_capex
    Bei MIP: reindex nach years-Reihenfolge
    Bei Single: ersetzt 'Single' durch 'CAPEX (Summe)'
    Erstellt go.Bar mit Hovertemplate und Layout
    
    Outputs: go.figure (Säulendiagramm Gesamtinvestitionen)
    """
    
    fig = go.Figure()
    if df_inv is None or df_inv.empty:
        fig.update_layout(title="Investitionen (Overnight CAPEX) (keine Daten)")
        return fig

    if years:
        order = [str(y) for y in years]
        agg = df_inv.groupby("period")["investment_capex"].sum().reindex(order).fillna(0.0)
        label_map = _investment_period_span_labels(years, horizon_end_year)
        x = [label_map.get(str(p), str(p)) for p in agg.index.tolist()]
        y = agg.values.tolist()
        title = "Gesamtinvestitionen: Zubau je Investitionsperiode (nicht annuisiert)"
        x_title = "Investitionsspanne"
    else:
        # Single-year: "Single" -> "CAPEX (Summe)"
        agg = df_inv.groupby("period")["investment_capex"].sum().fillna(0.0)

        if len(agg.index) == 1 and str(agg.index[0]) == "Single":
            x = ["CAPEX (Summe)"]
            y = [float(agg.iloc[0])]
        else:
            x = [("CAPEX (Summe)" if str(p) == "Single" else str(p)) for p in agg.index.tolist()]
            y = agg.values.tolist()

        title = "Gesamtinvestitionen (CAPEX (Summe), nicht annuisiert)"
        x_title = "Kostenart"

    fig.add_trace(go.Bar(
        x=x,
        y=y,
        hovertemplate="%{x}<br>%{y:.2f} EUR<extra></extra>",
        name="Investitionen",
        marker=dict(color=COST_COLOR_MAP.get("CAPEX")),
    ))

    fig.update_layout(
        title=title,
        xaxis_title=x_title,
        yaxis_title="Investitionen [EUR]",
        margin=dict(l=30, r=30, t=60, b=50),
        showlegend=True,
        legend_title="Kostenart",
    )
    return fig



def build_costs_df(n: pypsa.Network) -> pd.DataFrame:
    """
    Berechnet annualisierte CAPEX und OPEX (fix+variabel) je Komponente und Periode (nur für
    aktive Assets)
    
    Inputs: n: pypsa.Network
    
    Liest years und objective Snapshot-Weights
    Iteriert über COST_COMPONENTS und Assets mit positiver Nennleistung/ Kapazität
    Leitet build_year und end_year ab; bei MIP: berücksichtigt nur aktive Perioden
    CAPEX = capital_cost (annualisiert) * nom_i in jeder aktiven Periode
    Fix-OPEX = fixed_cost * nom_i; variabel via _variable_opex_by_period
    Sammelt Zeilen (period, component, name, base_name, label, capex, opex, opex_fix, opex_var)
    
    Outputs: DataFrame: Kosten je Asset und Periode
    """
    years = get_investment_years(n)
    weights = _get_objective_snapshot_weights(n)

    rows = []
    years_set = set(years)

    for comp_name in COST_COMPONENTS:
        if not hasattr(n, comp_name):
            continue
        static_df = getattr(n, comp_name)
        if static_df is None or static_df.empty:
            continue
        nom = _nominal_opt_series(comp_name, static_df).fillna(0.0).astype(float)
        cap_cost = _safe_cost_series(static_df, "capital_cost")
        fix_cost = _safe_cost_series(static_df, "fixed_cost")
        var_opex = _variable_opex_by_period(n, comp_name, static_df, years, weights)
        var_opex = _remove_duplicate_fuel_link_opex(n, comp_name, static_df, var_opex)

        for name in static_df.index:
            nom_i = float(nom.get(name, 0.0))
            if nom_i <= 0.0:
                continue

            base_name, _y_suffix = split_base_and_year(str(name), years_set)
            build_year = _infer_build_year(str(name), static_df, years)
            end_year = _infer_end_year(str(name), static_df, build_year)

            periods_iter = [str(y) for y in years] if years else ["Single"]

            for p in periods_iter:
                if years and build_year is not None:
                    p_int = int(p)
                    active = (p_int >= int(build_year)) and (p_int < end_year)
                    if not active:
                        continue

                capex = 0.0
                # CAPEX als Annuität: in jeder aktiven Periode ansetzen
                capex = float(cap_cost.get(name, 0.0)) * nom_i


                opex_fix = float(fix_cost.get(name, 0.0)) * nom_i
                opex_var = float(var_opex.at[p, name]) if (p in var_opex.index and name in var_opex.columns) else 0.0
                opex = opex_fix + opex_var

                if capex == 0.0 and opex == 0.0:
                    continue

                rows.append({
                    "period": str(p),
                    "component": comp_name,
                    "name": str(name),
                    "base_name": base_name,
                    "label": f"{comp_name}__{base_name}",
                    "capex": capex,
                    "opex": opex,
                    "opex_fix": opex_fix,
                    "opex_var": opex_var,
                })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out[(out["capex"].abs() + out["opex"].abs()) > 0.0].copy()
    return out



#%% CO2 / Emissionen

def _component_numeric_series(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    """
    Gibt Tabellenspalte sicher als Zahlenreihe aus.
    Wenn die Spalte fehlt oder Werte ungültig sind, werden diese durch einen Standardwert (0.0) ersetzt.
    Verhindert das Abstürzen durch einen ungültigen Wert.
    
    Inputs: df, col, default.
    Outputs: df, col.
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(default)
    return pd.Series(default, index=df.index, dtype=float)


def _component_string_series(df: pd.DataFrame, col: str, default: str = "") -> pd.Series:
    """
    Gibt DataFramespalte sicher als Textreihe aus.
    Wenn die Spalte fehlt oder Werte leer sind, nimmt sie den Standardtext ("") an.
    
    Inputs: df, col, default.
    Outputs: df, col.
    """
    if df is None or df.empty:
        return pd.Series(dtype="string")
    if col in df.columns:
        return df[col].fillna(default).astype(str)
    return pd.Series(default, index=df.index, dtype="string")

# Definiert Scope-Bergiffe
CO2_SCOPE_LABELS = {
    "scope_1": "direkte Emissionen (Scope 1)",
    "scope_2": "indirekte Emissionen (Scope 2)",
    "scope_3": "indirekte Vorkettenemissionen (Scope 3)",
}
# Reihenfolge der Scopes
CO2_SCOPE_ORDER = ["scope_1", "scope_2", "scope_3"]
CO2_SCOPE_COLORS = {
    "scope_1": px.colors.qualitative.Vivid[2] if len(px.colors.qualitative.Vivid) > 2 else "#2ca02c",
    "scope_2": px.colors.qualitative.Vivid[0] if len(px.colors.qualitative.Vivid) > 0 else "#1f77b4",
    "scope_3": px.colors.qualitative.Vivid[5] if len(px.colors.qualitative.Vivid) > 5 else "#8c564b",
}


def _normalise_text_token(*values) -> str:
    """
    Dient dazu Texte zu vereinheitlichen, ersetzt Umlaute und entfernt Sonderzeichen.
    
    Inputs: Einzelne Textwerte.
    Outputs: Einheitliche Texte.
    """
    text = " ".join(
        str(v)
        for v in values
        if v is not None and not (isinstance(v, float) and pd.isna(v))
    ).lower()
    replacements = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "\u00c3\u00a4": "ae", "\u00c3\u00b6": "oe",
        "\u00c3\u00bc": "ue", "\u00c3\u009f": "ss",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _co2_context_text(n: pypsa.Network, component: str, row: pd.Series, name: str, co2_source: str) -> str:
    """
    Bereitet CO2-bezogene Daten der Komponeten für einen einheitlichen Vergleichstext auf.
    
    Inputs: n, component, row, name, co2_source.
    Outputs: Normalisierter Textstring.
    """
    values = [component, name, co2_source, row.get("carrier", "")]
    for col in ("bus", "bus0", "bus1", "bus2", "bus3"):
        if col in row.index:
            values.append(row.get(col, ""))
    return _normalise_text_token(*values)


def _co2_energy_source_from_context(context: str) -> str:
    """
    Sucht nach Energieträgern der Komponenten.
    
    Inputs: Normalisierter Suchtext zu einer Komponente
    Outputs: Text mit der erkannten Energiequelle.
    """
    if any(tok in context for tok in ("gas", "erdgas", "methan", "biogas")):
        return "Gas"
    if any(tok in context for tok in ("wasserstoff", "hydrogen", " h2", "_h2")):
        return "Wasserstoff"
    if any(tok in context for tok in ("benzin", "benzol", "diesel", "heizoel", "oel", "fuel")):
        return "Flüssigbrennstoff"
    if any(tok in context for tok in ("kohle", "coal")):
        return "Kohle"
    if any(tok in context for tok in ("strom", "electric", "grid")):
        return "Strom"
    if any(tok in context for tok in ("fernwaerme", "waerme", "heat", "dampf", "steam")):
        return "Fernwärme"
    return "Sonstige"


def _co2_scope_from_dashboard(
    n: pypsa.Network,
    component: str,
    row: pd.Series,
    name: str,
    raw_scope: str,
    co2_source: str,
) -> tuple[str, str, str, str]:
    """
    Bestimmt Scope und direkt/indirekt Emissionen im Dashboard anhand von Quelle, Komponente und Carrier.

    Die PyPSA-Datei liefert weiterhin Faktoren, Preise und Ports. Die fachliche Zuordnung zu
    Scope 1/2/3 passiert hier, damit neue Energieträger später zentral ergänzt werden können.

    Inputs: PyPSA-Netzwerk, Komponententyp, Komponentenreihe, Name, Roh-Scope und CO2-Quelle.
    Outputs: Scope, Scope-Label, Wirkungsart und Energieträgerquelle.
    """
    context = _co2_context_text(n, component, row, name, co2_source)
    raw = _normalise_text_token(raw_scope)
    source = _co2_energy_source_from_context(context)

    fuel_like = source in {"Gas", "Wasserstoff", "Flüssigbrennstoff", "Kohle"}
    purchased_energy = source in {"Strom", "Fernwärme"}

    if component == "links" and fuel_like:
        scope = "scope_1"
    elif purchased_energy:
        scope = "scope_2"
    elif fuel_like:
        scope = "scope_3"
    elif "scope_1" in raw or raw == "direct":
        scope = "scope_1"
    elif "scope_2" in raw:
        scope = "scope_2"
    elif "scope_3" in raw or raw in {"upstream", "fuel_supply"}:
        scope = "scope_3"
    else:
        scope = "scope_3"

    scope_label = CO2_SCOPE_LABELS.get(scope, "Emissionen (Scope unklar)")
    emission_kind = (
        "Direkte Emissionen (Scope 1)"
        if scope == "scope_1"
        else "Indirekte Emissionen (Scopes 2+3)"
    )

    intensity_group = ""
    if source == "Strom" and scope == "scope_2":
        intensity_group = "Strom (indirekte Emissionen, Scope 2)"
    elif source == "Gas" and scope == "scope_1":
        intensity_group = "Gas (direkte Emissionen, Scope 1)"
    elif source not in {"Sonstige", "Fernwärme"}:
        intensity_group = f"{source} ({scope_label})"

    return scope, scope_label, emission_kind, intensity_group


def _get_dynamic_attr_df(n: pypsa.Network, comp_name: str, attr: str) -> pd.DataFrame | None:
    """
    Liest Attributs-DataFrame aus den verfügbaren Datenstrukturen aus.
    
    Inputs: n, comp_name, attr.
    Outputs: DataFrame mit Zeitreihenwerten oder None.
    """
    if not hasattr(n, "components") or not hasattr(n.components, comp_name):
        return None
    dyn = getattr(n.components, comp_name).dynamic
    return dyn.get(attr)


def _aggregate_weighted_energy_by_period(series: pd.Series, weights: pd.Series) -> pd.Series:
    """
    Erzeugt aus Leistungszeitreihe eine Energiemenge pro Investitionsperiode.
    
    Inputs: series, weights.
    Outputs: Series mit aufsummierter gewichteter Energie je Periode.
    """
    if series is None or len(series) == 0:
        return pd.Series(dtype=float)

    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    w = weights.reindex(s.index).fillna(0.0)
    energy = s.mul(w)

    if isinstance(energy.index, pd.MultiIndex):
        out = energy.groupby(level=0).sum()
        out.index = out.index.astype(str)
        return out.astype(float)

    return pd.Series({"Single": float(energy.sum())}, dtype=float)


def build_emissions_df(n: pypsa.Network) -> pd.DataFrame:

    """
    Berechnet die CO2-Emissionen, Wirkung, Scope und Kosten je Investitionsperiode und Komponente.
    
    Inputs: PyPSA-Netzwerk.
    Outputs: DataFrame mit berechneten CO2-Kennzahlen je Komponente und Investitionsperiode oder eine leere Tabelle als Fallback.
    """
    cols = [
        "period", "sector", "subcarrier", "component", "name", "base_name", "label",
        "flow_port", "co2_scope", "co2_scope_label", "emission_kind",
        "intensity_group", "co2_source", "energy_kwh", "emissions_kg",
        "emissions_t", "co2_price_eur_per_t", "co2_cost_eur",
    ]
    if n is None:
        return pd.DataFrame(columns=cols)

    rows = []
    years = get_investment_years(n)
    years_set = set(years)
    weights = _get_energy_weights(n)

    if hasattr(n, "generators") and n.generators is not None and not n.generators.empty:
        static_df = n.generators
        p_df = _get_dynamic_attr_df(n, "generators", "p")
        factors = _component_numeric_series(static_df, "co2_factor_kg_per_kwh", 0.0)
        prices = _component_numeric_series(static_df, "co2_price_eur_per_t", 0.0)
        scopes = _component_string_series(static_df, "co2_scope", "")
        sources = _component_string_series(static_df, "co2_source", "")

        if p_df is not None and not p_df.empty:
            for name, r in static_df.iterrows():
                factor = float(factors.get(name, 0.0))
                # Negative Faktoren erlauben CO2-Entnahmen/Removals; nur echte Nullen werden übersprungen
                if abs(factor) <= 1e-12 or name not in p_df.columns:
                    continue

                energy_by_period = _aggregate_weighted_energy_by_period(
                    p_df[name].clip(lower=0.0), weights
                )
                if energy_by_period.empty:
                    continue

                base_name, _ = split_base_and_year(str(name), years_set)
                sector, subcarrier = sector_subcarrier_from_component_row(n, "generators", r)
                co2_price = float(prices.get(name, 0.0))
                co2_source = str(sources.get(name, ""))
                co2_scope, co2_scope_label, emission_kind, intensity_group = _co2_scope_from_dashboard(
                    n, "generators", r, str(name), str(scopes.get(name, "")), co2_source
                )

                for period, energy_kwh in energy_by_period.items():
                    energy_kwh = float(energy_kwh)
                    if energy_kwh <= 0.0:
                        continue
                    emissions_kg = energy_kwh * factor
                    rows.append({
                        "period": str(period),
                        "sector": sector,
                        "subcarrier": subcarrier,
                        "component": "generators",
                        "name": str(name),
                        "base_name": base_name,
                        "label": f"generators__{base_name}",
                        "flow_port": "p",
                        "co2_scope": co2_scope,
                        "co2_scope_label": co2_scope_label,
                        "emission_kind": emission_kind,
                        "intensity_group": intensity_group,
                        "co2_source": co2_source,
                        "energy_kwh": energy_kwh,
                        "emissions_kg": emissions_kg,
                        "emissions_t": emissions_kg / 1000.0,
                        "co2_price_eur_per_t": co2_price,
                        "co2_cost_eur": (emissions_kg / 1000.0) * co2_price,
                    })

    if hasattr(n, "links") and n.links is not None and not n.links.empty:
        static_df = n.links
        factors = _component_numeric_series(static_df, "co2_factor_kg_per_kwh", 0.0)
        prices = _component_numeric_series(static_df, "co2_price_eur_per_t", 0.0)
        ports = _component_string_series(static_df, "co2_port", "p0")
        scopes = _component_string_series(static_df, "co2_scope", "")
        sources = _component_string_series(static_df, "co2_source", "")

        for name, r in static_df.iterrows():
            factor = float(factors.get(name, 0.0))
            # Negative Faktoren erlauben CO2-Entnahmen/Removals; nur echte Nullen werden übersprungen
            if abs(factor) <= 1e-12:
                continue

            in_attr = str(ports.get(name, "p0") or "p0")
            p_in_df = _get_dynamic_attr_df(n, "links", in_attr)
            if p_in_df is None or p_in_df.empty or name not in p_in_df.columns:
                continue

            input_by_period = _aggregate_weighted_energy_by_period(
                p_in_df[name].clip(lower=0.0), weights
            )
            if input_by_period.empty:
                continue

            output_specs = []
            for i in range(1, 10):
                bus_col = f"bus{i}"
                if bus_col not in static_df.columns:
                    continue
                bus = r.get(bus_col, None)
                if bus is None or pd.isna(bus) or str(bus).strip() == "":
                    continue

                p_out_df = _get_dynamic_attr_df(n, "links", f"p{i}")
                if p_out_df is None or p_out_df.empty or name not in p_out_df.columns:
                    continue

                output_by_period = _aggregate_weighted_energy_by_period(
                    (-p_out_df[name].clip(upper=0.0)), weights
                )
                if output_by_period.empty:
                    continue

                sector_i, subcarrier_i = sector_subcarrier_from_bus(n, str(bus))
                output_specs.append((f"p{i}", sector_i, subcarrier_i, output_by_period))

            base_name, _ = split_base_and_year(str(name), years_set)
            co2_price = float(prices.get(name, 0.0))
            co2_source = str(sources.get(name, ""))
            co2_scope, co2_scope_label, emission_kind, intensity_group = _co2_scope_from_dashboard(
                n, "links", r, str(name), str(scopes.get(name, "")), co2_source
            )

            fallback_bus = None
            for key in [f"bus{i}" for i in range(1, 10)] + ["bus0"]:
                v = r.get(key, None)
                if v is not None and not pd.isna(v) and str(v).strip() != "":
                    fallback_bus = str(v)
                    break
            fallback_sector, fallback_subcarrier = sector_subcarrier_from_bus(n, fallback_bus)

            periods = sorted(
                set(input_by_period.index.astype(str).tolist())
                | {str(idx) for _port, _sector, _subcarrier, out in output_specs for idx in out.index.tolist()}
            )

            for period in periods:
                input_energy_kwh = float(input_by_period.get(period, 0.0))
                if input_energy_kwh <= 0.0:
                    continue

                total_output_kwh = sum(float(out.get(period, 0.0)) for _port, _sector, _subcarrier, out in output_specs)
                if total_output_kwh <= 0.0:
                    emissions_kg = input_energy_kwh * factor
                    rows.append({
                        "period": str(period),
                        "sector": fallback_sector,
                        "subcarrier": fallback_subcarrier,
                        "component": "links",
                        "name": str(name),
                        "base_name": base_name,
                        "label": f"links__{base_name}",
                        "flow_port": in_attr,
                        "co2_scope": co2_scope,
                        "co2_scope_label": co2_scope_label,
                        "emission_kind": emission_kind,
                        "intensity_group": intensity_group,
                        "co2_source": co2_source,
                        "energy_kwh": input_energy_kwh,
                        "emissions_kg": emissions_kg,
                        "emissions_t": emissions_kg / 1000.0,
                        "co2_price_eur_per_t": co2_price,
                        "co2_cost_eur": (emissions_kg / 1000.0) * co2_price,
                    })
                    continue

                for out_port, sector_i, subcarrier_i, output_by_period in output_specs:
                    output_energy_kwh = float(output_by_period.get(period, 0.0))
                    if output_energy_kwh <= 0.0:
                        continue

                    share = output_energy_kwh / total_output_kwh
                    emissions_kg = input_energy_kwh * factor * share
                    rows.append({
                        "period": str(period),
                        "sector": sector_i,
                        "subcarrier": subcarrier_i,
                        "component": "links",
                        "name": str(name),
                        "base_name": base_name,
                        "label": f"links__{base_name}",
                        "flow_port": out_port,
                        "co2_scope": co2_scope,
                        "co2_scope_label": co2_scope_label,
                        "emission_kind": emission_kind,
                        "intensity_group": intensity_group,
                        "co2_source": co2_source,
                        "energy_kwh": output_energy_kwh,
                        "emissions_kg": emissions_kg,
                        "emissions_t": emissions_kg / 1000.0,
                        "co2_price_eur_per_t": co2_price,
                        "co2_cost_eur": (emissions_kg / 1000.0) * co2_price,
                    })

    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        return out
    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["period"])
    out = out[(out["energy_kwh"].abs() + out["emissions_kg"].abs()) > 0.0].copy()
    return out


def build_load_delivery_df(n: pypsa.Network) -> pd.DataFrame:
    """
    Erstellt den DataFrame für Energie jede Last in jeder Investitionsperiode.
    
    Inputs: PyPSA-Netzwerk.
    Outputs: DataFrame mit gelieferter Lastenergie je Periode.
    """
    cols = ["period", "sector", "subcarrier", "name", "energy_kwh"]
    if n is None or not hasattr(n, "loads") or n.loads is None or n.loads.empty:
        return pd.DataFrame(columns=cols)

    weights = _get_energy_weights(n)
    dyn = n.components.loads.dynamic if hasattr(n.components, "loads") else {}
    p_df = dyn.get("p")
    if p_df is None or p_df.empty:
        p_df = dyn.get("p_set")
    if p_df is None or p_df.empty:
        return pd.DataFrame(columns=cols)

    rows = []
    for name, r in n.loads.iterrows():
        if name not in p_df.columns:
            continue
        sector, subcarrier = sector_subcarrier_from_component_row(n, "loads", r)
        energy_by_period = _aggregate_weighted_energy_by_period(
            p_df[name].clip(lower=0.0), weights
        )
        for period, energy_kwh in energy_by_period.items():
            energy_kwh = float(energy_kwh)
            if energy_kwh <= 0.0:
                continue
            rows.append({
                "period": str(period),
                "sector": sector,
                "subcarrier": subcarrier,
                "name": str(name),
                "energy_kwh": energy_kwh,
            })

    return pd.DataFrame(rows, columns=cols)


def build_co2_intensity_scope_df(n: pypsa.Network, df_emissions: pd.DataFrame) -> pd.DataFrame:
    """
    Berechnte Gramm CO2 pro kWh in einer bestimmten Kategorie.
    
    Inputs: PyPSA-Netzwerk, df_emissions.
    Outputs: DataFrame mit CO2-Intensitäten je Periode und Kategorie.
    """
    cols = ["period", "category", "energy_kwh", "emissions_kg", "intensity_g_per_kwh"]
    if df_emissions is None or df_emissions.empty or "intensity_group" not in df_emissions.columns:
        return pd.DataFrame(columns=cols)

    d = df_emissions.copy()
    d["intensity_group"] = d["intensity_group"].fillna("").astype(str)
    d = d[d["intensity_group"].str.strip() != ""].copy()
    if d.empty:
        return pd.DataFrame(columns=cols)

    grouped = (
        d.groupby(["period", "intensity_group"])[["energy_kwh", "emissions_kg"]]
        .sum()
        .reset_index()
    )
    rows = []
    for _, r in grouped.iterrows():
        energy_kwh = float(r["energy_kwh"])
        emissions_kg = float(r["emissions_kg"])
        rows.append({
            "period": str(r["period"]),
            "category": str(r["intensity_group"]),
            "energy_kwh": energy_kwh,
            "emissions_kg": emissions_kg,
            "intensity_g_per_kwh": (emissions_kg / energy_kwh * 1000.0) if energy_kwh > 0.0 else np.nan,
        })

    return pd.DataFrame(rows, columns=cols)



def build_co2_period_scope_stack_fig(
    df: pd.DataFrame,
    years: list[int],
    value_col: str,
    unit: str,
    title: str,
    period_value: str | None = "all",
) -> go.Figure:
    """
    Erzeugt ein Diagramm, das CO2-Werte pro Investitionsperiode zeigt und dabei nach Scope oder Sektor stapelt.
    
    Inputs: df, years, value_col, unit, title, period_value.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df is None or df.empty or value_col not in df.columns:
        fig.update_layout(title=f"{title} (keine Daten)")
        return fig

    group_col = "co2_scope_label" if "co2_scope_label" in df.columns else "sector"
    d = df.groupby(["period", group_col])[value_col].sum().reset_index()
    if period_value not in (None, "", "all", "Alle"):
        resolved_period = _resolve_df_period(d, str(period_value)) or str(period_value)
        d = d[d["period"].astype(str) == str(resolved_period)].copy()
        order = [str(resolved_period)]
    else:
        order = [str(y) for y in years] if years else sorted(d["period"].astype(str).unique().tolist()) or ["Single"]

    if group_col == "co2_scope_label":
        present = set(d[group_col].astype(str).tolist())
        groups = [CO2_SCOPE_LABELS[s] for s in CO2_SCOPE_ORDER if CO2_SCOPE_LABELS[s] in present]
        groups += [g for g in sorted(present) if g not in groups]
        colors = {CO2_SCOPE_LABELS[s]: CO2_SCOPE_COLORS.get(s) for s in CO2_SCOPE_ORDER}
    else:
        groups = SECTORS
        colors = {
            "Strom": px.colors.qualitative.Vivid[0],
            "Wärme": px.colors.qualitative.Vivid[1] if len(px.colors.qualitative.Vivid) > 1 else "#ff7f0e",
            "Sonstige": px.colors.qualitative.Vivid[2] if len(px.colors.qualitative.Vivid) > 2 else "#2ca02c",
        }

    for group_name in groups:
        s = d[d[group_col].astype(str) == group_name].set_index("period")[value_col].reindex(order).fillna(0.0)
        if float(s.abs().sum()) <= 0.0:
            continue
        fig.add_trace(go.Bar(
            name=group_name,
            x=order,
            y=s.values,
            marker=dict(color=colors.get(group_name)),
            hovertemplate="%{x}<br>" + group_name + f": %{{y:.2f}} {unit}<extra></extra>",
        ))

    fig.update_layout(
        title=title,
        barmode="stack",
        xaxis_title="Investitionsperiode",
        yaxis_title=f"Wert [{unit}]",
        margin=dict(l=30, r=30, t=60, b=50),
        legend_title="Scope" if group_col == "co2_scope_label" else "Sektor",
    )
    return fig


def build_co2_intensity_scope_fig(
    df_intensity: pd.DataFrame,
    years: list[int],
    period_value: str | None = "all",
) -> go.Figure:
    """
    Erzeugt ein Diagramm, das zeigt, wieviel Gramm CO2 pro kWh bei verschiedenen Energieträgern oder Scopes entstehen.
    
    Inputs: df_intensity, years, period_value.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_intensity is None or df_intensity.empty or "category" not in df_intensity.columns:
        fig.update_layout(title="CO2-Intensität (keine Daten)")
        return fig

    d = df_intensity.copy()
    if period_value not in (None, "", "all", "Alle"):
        resolved_period = _resolve_df_period(d, str(period_value)) or str(period_value)
        d = d[d["period"].astype(str) == str(resolved_period)].copy()
        order = [str(resolved_period)]
    else:
        order = [str(y) for y in years] if years else sorted(d["period"].astype(str).unique().tolist()) or ["Single"]
    preferred = [
        "Strom (indirekte Emissionen, Scope 2)",
        "Gas (direkte Emissionen, Scope 1)",
    ]
    present = set(d["category"].astype(str).tolist())
    categories = [c for c in preferred if c in present] + [c for c in sorted(present) if c not in preferred]
    palette = px.colors.qualitative.Vivid + px.colors.qualitative.Bold
    colors = {cat: palette[i % len(palette)] for i, cat in enumerate(categories)}
    colors["Strom (indirekte Emissionen, Scope 2)"] = CO2_SCOPE_COLORS.get("scope_2")
    colors["Gas (direkte Emissionen, Scope 1)"] = CO2_SCOPE_COLORS.get("scope_1")

    for category in categories:
        s = d[d["category"].astype(str) == category].set_index("period")["intensity_g_per_kwh"].reindex(order)
        if s.dropna().empty:
            continue
        fig.add_trace(go.Bar(
            name=category,
            x=order,
            y=s.fillna(0.0).values,
            marker=dict(color=colors.get(category)),
            hovertemplate="%{x}<br>" + category + ": %{y:.2f} g CO2/kWh<extra></extra>",
        ))

    fig.update_layout(
        title="CO2-Intensitäten nach Energieträger und Scope",
        barmode="group",
        xaxis_title="Investitionsperiode",
        yaxis_title="Intensität [g CO2/kWh]",
        margin=dict(l=30, r=30, t=60, b=50),
        legend_title="Bilanzraum",
    )
    return fig


#%% Wirtschaftlichkeit (erweiterte Kennzahlen)

def _storage_group_name(base_name: str) -> str:
    """
    Entfernt am Ende eines Namens die Zusätze.
    Z.B. _Laden oder _Entladen
    
    Inputs: base_name.
    Outputs: bereinigte Speicher-Gruppennamen.
    """
    s = str(base_name)
    s = re.sub(r"_(Laden|Entladen)$", "", s, flags=re.IGNORECASE)
    return s


def _coerce_discount_rate_value(value) -> float | None:
    """
    Wandelt coerce discount rate value robust in den benötigten Datentyp um.
    
    Inputs: value.
    Outputs: Gültiger Zinssatz oder None.
    """
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(rate):
        return None
    return rate


def _extract_project_discount_rate_from_meta(meta) -> float | None:
    """
    Liest aus den Metadtaen den verwendeten Zinssatz.
    
    Inputs: Metadaten aus PyPSA.
    Outputs: Gefundener Zinssatz oder None.
    """
    if meta is None:
        return None

    if isinstance(meta, str):
        text = meta.strip()
        if not text:
            return None
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
            except Exception:
                continue
            rate = _extract_project_discount_rate_from_meta(parsed)
            if rate is not None:
                return rate
        match = re.search(
            r'"?(?:economic_discount_rate|project_discount_rate|discount_rate)"?\s*:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)',
            text,
        )
        return _coerce_discount_rate_value(match.group(1)) if match else None

    if isinstance(meta, pd.Series):
        meta = meta.to_dict()

    if isinstance(meta, dict):
        for key in ("economic_discount_rate", "project_discount_rate", "discount_rate"):
            if key in meta:
                rate = _coerce_discount_rate_value(meta.get(key))
                if rate is not None:
                    return rate
        return None

    return None


def _infer_project_discount_rate(n: pypsa.Network) -> float:
    """
    Sucht, welcher Diskontierungszins im Projekt verwendet wurde.
    
    Inputs: PyPSA-Netzwerk.
    Outputs: Zinssatz als float-Zahl.
    """
    meta_rate = _extract_project_discount_rate_from_meta(getattr(n, "meta", None))
    if meta_rate is not None:
        return meta_rate

    rates = []
    for comp_name in COST_COMPONENTS:
        if not hasattr(n, comp_name):
            continue
        df = getattr(n, comp_name)
        if df is None or df.empty or "discount_rate" not in df.columns:
            continue
        vals = pd.to_numeric(df["discount_rate"], errors="coerce")
        vals = vals[np.isfinite(vals)]
        if vals.empty:
            continue
        rates.extend(vals.astype(float).tolist())

    if not rates:
        return DEFAULT_DISCOUNT_RATE

    non_zero_rates = [float(v) for v in rates if abs(float(v)) > 1e-12]
    if non_zero_rates:
        rates = non_zero_rates

    uniq = sorted({round(float(v), 8) for v in rates})
    if len(uniq) == 1:
        return float(uniq[0])
    return float(np.median(rates))


def _select_project_discount_rate(*candidates) -> float:
    """
    Nimmt mehrere mögliche Zinssätze und wählt den ersten brauchbaren aus.
    
    Inputs: Mögliche Zinssätze.
    Outputs: Gültiger Zinssatz als float-Zahl.
    """
    valid = []
    for value in candidates:
        try:
            rate = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(rate):
            continue
        valid.append(rate)
    if not valid:
        return DEFAULT_DISCOUNT_RATE
    non_zero = [rate for rate in valid if abs(rate) > 1e-12]
    return float(non_zero[0] if non_zero else valid[0])


def _analysis_horizon_end_year(df_life: pd.DataFrame, years: list[int]) -> int | None:
    """
    Bestimmt das Endjahr des Betrachtungszeitraums.
    
    Inputs: df_life, years.
    Outputs: Endjahr als int.
    """
    candidates = [int(max(years))] if years else []
    if df_life is not None and not df_life.empty and "end_year" in df_life.columns:
        vals = pd.to_numeric(df_life["end_year"], errors="coerce")
        vals = vals[np.isfinite(vals)]
        if not vals.empty:
            candidates.append(int(math.ceil(float(vals.max()))))
    return max(candidates) if candidates else None


def _period_for_year(year: int, years: list[int]) -> str:
    """
    Ordnet ein normales Jahr der passenden Investitionsperiode zu.
    
    Inputs: year, years.
    Outputs: Periodenname als Text, z. B. "2030"
    """
    if not years:
        return "Single"
    years_sorted = sorted(int(y) for y in years)
    candidates = [y for y in years_sorted if y <= int(year)]
    return str(candidates[-1] if candidates else years_sorted[0])


def _yearly_period_cost_components_for_year(
    df_total_cost: pd.DataFrame,
    years: list[int],
    year: int,
) -> tuple[float, float, float]:
    """
    Liefert CAPEX (als Annuität), OPEX und CO2-Kosten für ein einzelnes Kalenderjahr.

    Die Jahreswerte werden dabei bewusst genauso als periodische Stufenfunktion
    rekonstruiert wie im Diagramm "Gesamtkosten je Investitionsperiode". Damit
    basieren Cashflow, Delta-Cashflow und die daraus abgeleiteten Kennwerte auf
    derselben annualisierten Kostenlogik wie die übrigen Wirtschaftlichkeitsplots.

    Inputs: Gesamtkostentabelle, Investitionsperioden und Kalenderjahr.
    Outputs: CAPEX-Annuität, OPEX und CO2-Kosten als Jahreswerte.
    """
    if df_total_cost is None or df_total_cost.empty:
        return 0.0, 0.0, 0.0

    d = df_total_cost.copy()
    d["period"] = d["period"].astype(str)
    requested_period = _period_for_year(int(year), years)
    resolved_period = _resolve_df_period(d, requested_period) or requested_period
    chosen_df = d[d["period"].astype(str) == str(resolved_period)].copy()
    if chosen_df.empty:
        return 0.0, 0.0, 0.0

    capex = float(pd.to_numeric(chosen_df.get("capex", 0.0), errors="coerce").fillna(0.0).sum())
    opex = float(pd.to_numeric(chosen_df.get("opex", 0.0), errors="coerce").fillna(0.0).sum())
    co2_cost = float(pd.to_numeric(chosen_df.get("co2_cost", 0.0), errors="coerce").fillna(0.0).sum())
    return capex, opex, co2_cost


def _available_periods_from_df(df: pd.DataFrame) -> list[str]:
    """
    Schaut welche Investitionsperioden vorhanden sind.
    
    Inputs: df.
    Outputs: Liste mit vorhandenen Perioden als Text.
    """
    if df is None or df.empty or "period" not in df.columns:
        return []
    vals = [
        str(v).strip()
        for v in df["period"].dropna().astype(str).tolist()
        if str(v).strip() != ""
    ]
    if not vals:
        return []
    return sorted(set(vals), key=lambda x: (not str(x).isdigit(), str(x)))


def _resolve_period_value(requested_period: str | None, available_periods: list[str]) -> str | None:
    """
    Ordnet eine gewünschte Periode auf eine tatsächlich vorhandene Periode zu.
    Für den Periodenfilter.
    
    Inputs: requested_period, available_periods.
    Outputs: Vorhandene Periode als Text.
    """
    periods = [str(p).strip() for p in available_periods if str(p).strip() != ""]
    if not periods:
        return None

    requested = None if requested_period in (None, "") else str(requested_period).strip()
    if requested is None:
        return periods[0]
    if requested in periods:
        return requested
    if len(periods) == 1:
        return periods[0]

    try:
        requested_num = int(float(requested))
    except Exception:
        requested_num = None

    numeric_periods: list[tuple[int, str]] = []
    for token in periods:
        try:
            numeric_periods.append((int(float(token)), token))
        except Exception:
            continue
    if requested_num is not None and numeric_periods:
        numeric_periods.sort(key=lambda item: (abs(item[0] - requested_num), item[0]))
        return numeric_periods[0][1]

    if "Single" in periods:
        return "Single"
    return periods[0]


def _resolve_df_period(df: pd.DataFrame, requested_period: str | None) -> str | None:
    """
    Sucht im DataFrame die vorhandenen Perioden und ordnet die gewünschte Periode einer gültigen vorhandenen Periode zu.
    
    Inputs: df, requested_period.
    Outputs: Passende vorhandene Periode als Text.
    """
    return _resolve_period_value(requested_period, _available_periods_from_df(df))


def _resolve_state_period(st: dict, requested_period: str | None) -> str | None:
    """
    Bestimmt aus dem Dashboard-State, welche Periode wirklich verwendet werden soll.
    
    Inputs: st, requested_period.
    Outputs: Gültige Periode als Text.
    """
    if st is None or (not st.get("ok", False)):
        return None
    years = st.get("years", [])
    if years:
        return _resolve_period_value(requested_period, [str(int(y)) for y in years])
    return "Single"


def _period_label_for_title(base_period: str | None, cmp_period: str | None) -> str:
    """
    Erzeugt einen Text , mit dem Inhalt, welche Perioden gerade verglichen werden.
    Dieser kann in einen Titel übernommen werden.
    
    Inputs: base_period, cmp_period.
    Outputs: Textlabel für Diagrammtitel oder Überschriften.
    """
    if base_period is None and cmp_period is None:
        return "keine Periode"
    if base_period == cmp_period:
        return str(base_period)
    return f"Basis: {base_period} | Vergleich: {cmp_period}"


def _with_opex_including_co2(df: pd.DataFrame) -> pd.DataFrame:
    """
    Erzeugt ein DataFrame mit OPEX inklusive CO2-Kosten und Gesamtkosten inklusive CO2.
    
    Inputs: df.
    Outputs: Neuer DataFrame mit zusätzlichen Kostenspalten.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    co2_in_opex = _co2_costs_already_in_opex_from_df(df)
    d = df.copy()
    d.attrs.update(getattr(df, "attrs", {}))
    for col in ("capex", "opex", "co2_cost"):
        if col not in d.columns:
            d[col] = 0.0
        d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0.0)
    d["opex_incl_co2"] = (
        d["opex"]
        if co2_in_opex
        else d["opex"] + d["co2_cost"]
    )
    d["total_cost_incl_co2"] = d["capex"] + d["opex_incl_co2"]
    return d


def _investment_period_span_labels(years: list[int], horizon_end_year: int | None = None) -> dict[str, str]:
    """
    Erzeugt aus einzelnen Investitionsjahren lesbare Zeiträume.
    
    Inputs: years, horizon_end_year.
    Outputs: Dictionary mit Periode -> Zeitraum-Label.
    """
    if not years:
        return {}
    ys = sorted(int(y) for y in years)
    labels = {}
    for idx, start in enumerate(ys):
        if idx < len(ys) - 1:
            end = ys[idx + 1] - 1
        else:
            end = int(horizon_end_year) if horizon_end_year is not None else start
            if end < start:
                end = start
        labels[str(start)] = f"{start}-{end}" if end != start else str(start)
    return labels


def build_total_cost_df(
    df_cost: pd.DataFrame,
    df_emissions: pd.DataFrame,
    co2_costs_already_in_opex: bool | None = None,
) -> pd.DataFrame:
    """
    Kombiniert normale Kostentabelle mit CO₂-Kostentabelle und berechnet daraus die Gesamtkosten.
    
    Inputs: df_cost, df_emissions, co2_costs_already_in_opex.
    Outputs: DataFrame mit Gesamtkosten je Komponente und Periode.
    """
    cols = [
        "period", "component", "name", "base_name", "label",
        "capex", "opex", "opex_fix", "opex_var", "co2_cost", "emissions_t", "total_cost",
    ]

    keys = ["period", "component", "name", "base_name", "label"]

    if df_cost is None or df_cost.empty:
        cost = pd.DataFrame(columns=keys + ["capex", "opex", "opex_fix", "opex_var"])
    else:
        cost = (
            df_cost.groupby(keys)[["capex", "opex", "opex_fix", "opex_var"]]
            .sum()
            .reset_index()
        )

    if df_emissions is None or df_emissions.empty:
        emis = pd.DataFrame(columns=keys + ["co2_cost", "emissions_t"])
    else:
        emis = (
            df_emissions.groupby(keys)[["co2_cost_eur", "emissions_t"]]
            .sum()
            .reset_index()
            .rename(columns={"co2_cost_eur": "co2_cost"})
        )

    out = cost.merge(emis, on=keys, how="outer")
    if out.empty:
        return pd.DataFrame(columns=cols)

    for col in ("capex", "opex", "opex_fix", "opex_var", "co2_cost", "emissions_t"):
        out[col] = pd.to_numeric(out.get(col, 0.0), errors="coerce").fillna(0.0)

    co2_in_opex = (
        CO2_COSTS_ALREADY_INCLUDED_IN_OPEX
        if co2_costs_already_in_opex is None
        else bool(co2_costs_already_in_opex)
    )

    out["total_cost"] = (
        out["capex"] + out["opex"]
        if co2_in_opex
        else out["capex"] + out["opex"] + out["co2_cost"]
    )
    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["period"])
    out = out[(out["capex"].abs() + out["opex"].abs() + out["co2_cost"].abs()) > 0.0].copy()
    result = out[cols].copy()
    result.attrs["co2_costs_already_in_opex"] = co2_in_opex
    return result


def build_output_energy_df(n: pypsa.Network) -> pd.DataFrame:
    """
    Erstellt den DataFrame für die Energie die je Komponente pro Investitionsperiode verbraucht/erzeugt wurde.
    
    Inputs: PyPSA-Netzwerk.
    Outputs: DataFrame mit erzeugter/abgegebener Energie je Komponente und Periode.
    """
    cols = [
        "period", "sector", "subcarrier", "component", "name", "base_name", "label",
        "flow_port", "energy_kwh",
    ]
    if n is None:
        return pd.DataFrame(columns=cols)

    rows = []
    years = get_investment_years(n)
    years_set = set(years)
    weights = _get_energy_weights(n)

    if hasattr(n, "generators") and n.generators is not None and not n.generators.empty:
        p_df = _get_dynamic_attr_df(n, "generators", "p")
        if p_df is not None and not p_df.empty:
            for name, r in n.generators.iterrows():
                if name not in p_df.columns:
                    continue
                energy_by_period = _aggregate_weighted_energy_by_period(
                    p_df[name].clip(lower=0.0), weights
                )
                if energy_by_period.empty:
                    continue
                base_name, _ = split_base_and_year(str(name), years_set)
                sector, subcarrier = sector_subcarrier_from_component_row(n, "generators", r)
                for period, energy_kwh in energy_by_period.items():
                    energy_kwh = float(energy_kwh)
                    if energy_kwh <= 0.0:
                        continue
                    rows.append({
                        "period": str(period),
                        "sector": sector,
                        "subcarrier": subcarrier,
                        "component": "generators",
                        "name": str(name),
                        "base_name": base_name,
                        "label": f"generators__{base_name}",
                        "flow_port": "p",
                        "energy_kwh": energy_kwh,
                    })

    if hasattr(n, "storage_units") and n.storage_units is not None and not n.storage_units.empty:
        p_df = _get_dynamic_attr_df(n, "storage_units", "p")
        if p_df is not None and not p_df.empty:
            for name, r in n.storage_units.iterrows():
                if name not in p_df.columns:
                    continue
                energy_by_period = _aggregate_weighted_energy_by_period(
                    p_df[name].clip(lower=0.0), weights
                )
                if energy_by_period.empty:
                    continue
                base_name, _ = split_base_and_year(str(name), years_set)
                sector, subcarrier = sector_subcarrier_from_component_row(n, "storage_units", r)
                for period, energy_kwh in energy_by_period.items():
                    energy_kwh = float(energy_kwh)
                    if energy_kwh <= 0.0:
                        continue
                    rows.append({
                        "period": str(period),
                        "sector": sector,
                        "subcarrier": subcarrier,
                        "component": "storage_units",
                        "name": str(name),
                        "base_name": base_name,
                        "label": f"storage_units__{base_name}",
                        "flow_port": "p",
                        "energy_kwh": energy_kwh,
                    })

    if hasattr(n, "links") and n.links is not None and not n.links.empty:
        static_df = n.links
        for name, r in static_df.iterrows():
            base_name, _ = split_base_and_year(str(name), years_set)
            for i in range(1, 10):
                bus_col = f"bus{i}"
                if bus_col not in static_df.columns:
                    continue
                bus = r.get(bus_col, None)
                if bus is None or pd.isna(bus) or str(bus).strip() == "":
                    continue

                attr = f"p{i}"
                p_out_df = _get_dynamic_attr_df(n, "links", attr)
                if p_out_df is None or p_out_df.empty or name not in p_out_df.columns:
                    continue

                output_by_period = _aggregate_weighted_energy_by_period(
                    (-p_out_df[name].clip(upper=0.0)), weights
                )
                if output_by_period.empty:
                    continue

                sector_i, subcarrier_i = sector_subcarrier_from_bus(n, str(bus))
                for period, energy_kwh in output_by_period.items():
                    energy_kwh = float(energy_kwh)
                    if energy_kwh <= 0.0:
                        continue
                    rows.append({
                        "period": str(period),
                        "sector": sector_i,
                        "subcarrier": subcarrier_i,
                        "component": "links",
                        "name": str(name),
                        "base_name": base_name,
                        "label": f"links__{base_name}",
                        "flow_port": attr,
                        "energy_kwh": energy_kwh,
                    })

    return pd.DataFrame(rows, columns=cols)


# Begrenzt, wie oft das Dashboard Kosten entlang von Energieflüssen weiterverteilt.
TECH_COST_FLOW_ITERATIONS = 6


def build_output_flow_df(n: pypsa.Network) -> pd.DataFrame:
    """
    Erstellt den DataFrame für output flow.
    
    Inputs: PyPSA-Netzwerk.
    Outputs: DataFrame mit Energieflüssen von Komponenten zu Ausgangsbussen.
    """
    cols = [
        "period", "sector", "subcarrier", "component", "name", "base_name", "label",
        "input_bus", "output_bus", "flow_port", "energy_kwh",
    ]
    if n is None:
        return pd.DataFrame(columns=cols)

    rows = []
    years = get_investment_years(n)
    years_set = set(years)
    weights = _get_energy_weights(n)

    if hasattr(n, "generators") and n.generators is not None and not n.generators.empty:
        p_df = _get_dynamic_attr_df(n, "generators", "p")
        if p_df is not None and not p_df.empty:
            for name, r in n.generators.iterrows():
                if name not in p_df.columns:
                    continue
                energy_by_period = _aggregate_weighted_energy_by_period(p_df[name].clip(lower=0.0), weights)
                if energy_by_period.empty:
                    continue
                base_name, _ = split_base_and_year(str(name), years_set)
                bus = r.get("bus", "")
                sector, subcarrier = sector_subcarrier_from_bus(n, bus)
                for period, energy_kwh in energy_by_period.items():
                    energy_kwh = float(energy_kwh)
                    if energy_kwh <= 0.0:
                        continue
                    rows.append({
                        "period": str(period),
                        "sector": sector,
                        "subcarrier": subcarrier,
                        "component": "generators",
                        "name": str(name),
                        "base_name": base_name,
                        "label": f"generators__{base_name}",
                        "input_bus": "",
                        "output_bus": str(bus),
                        "flow_port": "p",
                        "energy_kwh": energy_kwh,
                    })

    if hasattr(n, "storage_units") and n.storage_units is not None and not n.storage_units.empty:
        p_df = _get_dynamic_attr_df(n, "storage_units", "p")
        if p_df is not None and not p_df.empty:
            for name, r in n.storage_units.iterrows():
                if name not in p_df.columns:
                    continue
                energy_by_period = _aggregate_weighted_energy_by_period(p_df[name].clip(lower=0.0), weights)
                if energy_by_period.empty:
                    continue
                base_name, _ = split_base_and_year(str(name), years_set)
                bus = r.get("bus", "")
                sector, subcarrier = sector_subcarrier_from_bus(n, bus)
                for period, energy_kwh in energy_by_period.items():
                    energy_kwh = float(energy_kwh)
                    if energy_kwh <= 0.0:
                        continue
                    rows.append({
                        "period": str(period),
                        "sector": sector,
                        "subcarrier": subcarrier,
                        "component": "storage_units",
                        "name": str(name),
                        "base_name": base_name,
                        "label": f"storage_units__{base_name}",
                        "input_bus": str(bus),
                        "output_bus": str(bus),
                        "flow_port": "p",
                        "energy_kwh": energy_kwh,
                    })

    if hasattr(n, "links") and n.links is not None and not n.links.empty:
        static_df = n.links
        for name, r in static_df.iterrows():
            base_name, _ = split_base_and_year(str(name), years_set)
            input_bus = str(r.get("bus0", "") or "")
            for i in range(1, 10):
                bus_col = f"bus{i}"
                if bus_col not in static_df.columns:
                    continue
                output_bus = r.get(bus_col, None)
                if output_bus is None or pd.isna(output_bus) or str(output_bus).strip() == "":
                    continue
                attr = f"p{i}"
                p_out_df = _get_dynamic_attr_df(n, "links", attr)
                if p_out_df is None or p_out_df.empty or name not in p_out_df.columns:
                    continue
                output_by_period = _aggregate_weighted_energy_by_period(
                    (-p_out_df[name].clip(upper=0.0)), weights
                )
                if output_by_period.empty:
                    continue
                sector_i, subcarrier_i = sector_subcarrier_from_bus(n, str(output_bus))
                for period, energy_kwh in output_by_period.items():
                    energy_kwh = float(energy_kwh)
                    if energy_kwh <= 0.0:
                        continue
                    rows.append({
                        "period": str(period),
                        "sector": sector_i,
                        "subcarrier": subcarrier_i,
                        "component": "links",
                        "name": str(name),
                        "base_name": base_name,
                        "label": f"links__{base_name}",
                        "input_bus": input_bus,
                        "output_bus": str(output_bus),
                        "flow_port": attr,
                        "energy_kwh": energy_kwh,
                    })

    return pd.DataFrame(rows, columns=cols)


def _link_input_energy_lookup(n: pypsa.Network, weights: pd.Series) -> dict[tuple[str, str], float]:
    """
    Berechnet, wie viel Energie bei jedem Link am Eingang p0 hineingeht.
    
    Inputs: PyPSA-Netzwerk, weights.
    Outputs: Dictionary mit Eingangsenergie je Link und Periode.
    """
    lookup: dict[tuple[str, str], float] = {}
    if n is None or not hasattr(n, "links") or n.links is None or n.links.empty:
        return lookup
    p_in_df = _get_dynamic_attr_df(n, "links", "p0")
    if p_in_df is None or p_in_df.empty:
        return lookup
    for name in n.links.index:
        if name not in p_in_df.columns:
            continue
        energy_by_period = _aggregate_weighted_energy_by_period(p_in_df[name].clip(lower=0.0), weights)
        for period, energy_kwh in energy_by_period.items():
            lookup[(str(period), str(name))] = float(energy_kwh)
    return lookup


def build_technology_output_cost_df(
    n: pypsa.Network,
    df_cost: pd.DataFrame,
    df_emissions: pd.DataFrame,
    co2_costs_already_in_opex: bool | None = None,
) -> pd.DataFrame:
    """
    Verteilt Kosten einer Technologie auf ihre abgegebene Energie.
    
    Inputs: n, df_cost, df_emissions, co2_costs_already_in_opex.
    Outputs: DataFrame mit Kosten je erzeugter/gelieferter Output-Energie.
    """
    cols = [
        "period", "sector", "subcarrier", "component", "name", "base_name", "label",
        "flow_port", "input_bus", "output_bus", "energy_kwh", "share",
        "capex", "opex", "co2_cost", "input_cost", "total_cost",
    ]
    df_energy = build_output_flow_df(n)
    df_total = build_total_cost_df(df_cost, df_emissions, co2_costs_already_in_opex)
    if df_energy.empty or df_total.empty:
        return pd.DataFrame(columns=cols)

    totals = (
        df_energy.groupby(["period", "component", "name"])["energy_kwh"]
        .sum()
        .reset_index()
        .rename(columns={"energy_kwh": "asset_energy_kwh"})
    )
    d = df_energy.merge(totals, on=["period", "component", "name"], how="left")
    d["share"] = np.where(d["asset_energy_kwh"] > 0.0, d["energy_kwh"] / d["asset_energy_kwh"], 0.0)

    key_cols = ["period", "component", "name", "base_name", "label"]
    d = d.merge(
        df_total[key_cols + ["capex", "opex", "co2_cost", "total_cost"]],
        on=key_cols,
        how="left",
    )
    for col in ("capex", "opex", "co2_cost", "total_cost"):
        d[f"own_{col}"] = pd.to_numeric(d[col], errors="coerce").fillna(0.0) * d["share"]

    d["input_cost"] = 0.0
    d["capex"] = d["own_capex"]
    d["opex"] = d["own_opex"]
    d["co2_cost"] = d["own_co2_cost"]
    d["total_cost"] = d["own_total_cost"]

    input_lookup = _link_input_energy_lookup(n, _get_energy_weights(n))
    bus_rates: dict[tuple[str, str], float] = {}

    for _ in range(TECH_COST_FLOW_ITERATIONS):
        current = d.copy()
        current["input_cost"] = 0.0
        link_mask = current["component"].astype(str).eq("links")
        if link_mask.any():
            input_costs = []
            for _, r in current.loc[link_mask].iterrows():
                period = str(r["period"])
                name = str(r["name"])
                input_bus = str(r.get("input_bus", "") or "")
                input_energy = input_lookup.get((period, name), 0.0)
                rate = bus_rates.get((period, input_bus), 0.0)
                input_costs.append(float(input_energy) * float(rate) * float(r.get("share", 0.0)))
            current.loc[link_mask, "input_cost"] = input_costs

        current["capex"] = current["own_capex"]
        current["opex"] = current["own_opex"] + current["input_cost"]
        current["co2_cost"] = current["own_co2_cost"]
        current["total_cost"] = current["own_total_cost"] + current["input_cost"]

        rate_source = current[
            (current["output_bus"].astype(str).str.strip() != "")
            & (pd.to_numeric(current["energy_kwh"], errors="coerce").fillna(0.0) > 0.0)
        ].copy()
        grouped = (
            rate_source.groupby(["period", "output_bus"])[["total_cost", "energy_kwh"]]
            .sum()
            .reset_index()
        )
        new_rates = {
            (str(r["period"]), str(r["output_bus"])): (
                float(r["total_cost"]) / float(r["energy_kwh"])
                if float(r["energy_kwh"]) > 0.0 else 0.0
            )
            for _, r in grouped.iterrows()
        }
        max_delta = max(
            [abs(new_rates.get(k, 0.0) - bus_rates.get(k, 0.0)) for k in set(new_rates) | set(bus_rates)]
            or [0.0]
        )
        d = current
        bus_rates = new_rates
        if max_delta <= 1e-9:
            break

    result = d[cols].copy()
    result.attrs.update(getattr(df_total, "attrs", {}))
    return result


def build_lcoe_df(
    n: pypsa.Network,
    df_cost: pd.DataFrame,
    df_emissions: pd.DataFrame,
    co2_costs_already_in_opex: bool | None = None,
) -> pd.DataFrame:
    """
    Berechnet Stromgestehungskosten je strombezogener Technologie und Periode.
    
    Inputs: n, df_cost, df_emissions, co2_costs_already_in_opex.
    Outputs: DataFrame mit spezifischen Energiekosten je Technologie und Periode.
    """
    cols = [
        "period", "sector", "subcarrier", "label", "energy_kwh",
        "capex", "opex", "co2_cost", "total_cost",
        "lcoe_eur_per_kwh", "lcoe_eur_per_mwh",
    ]
    d = build_technology_output_cost_df(n, df_cost, df_emissions, co2_costs_already_in_opex)
    if d.empty:
        return pd.DataFrame(columns=cols)

    out = (
        d.groupby(["period", "sector", "subcarrier", "label"])[["energy_kwh", "capex", "opex", "co2_cost", "total_cost"]]
        .sum()
        .reset_index()
    )
    out["lcoe_eur_per_kwh"] = np.where(out["energy_kwh"] > 0.0, out["total_cost"] / out["energy_kwh"], np.nan)
    out["lcoe_eur_per_mwh"] = out["lcoe_eur_per_kwh"] * 1000.0
    out = out[
        (out["energy_kwh"] > 0.0)
        & ((out["capex"].abs() + out["opex"].abs() + out["co2_cost"].abs()) > 0.0)
    ].copy()
    return out[cols]


def build_sector_lcoe_df(
    n: pypsa.Network,
    df_cost: pd.DataFrame,
    df_emissions: pd.DataFrame,
    co2_costs_already_in_opex: bool | None = None,
) -> pd.DataFrame:
    """
    Berechnet sektorbezogene spezifische Gestehungskosten für Strom und Wärme.
    
    Inputs: n, df_cost, df_emissions, co2_costs_already_in_opex.
    Outputs: DataFrame mit spezifischen Energiekosten je Sektor und Periode.
    """
    cols = [
        "period", "sector", "energy_kwh",
        "capex", "opex", "co2_cost", "total_cost",
        "lcoe_eur_per_kwh", "lcoe_eur_per_mwh",
    ]
    d_cost = build_technology_output_cost_df(n, df_cost, df_emissions, co2_costs_already_in_opex)
    d_load = build_load_delivery_df(n)
    if d_cost.empty or d_load.empty:
        return pd.DataFrame(columns=cols)

    d_cost = d_cost[~d_cost["subcarrier"].astype(str).str.contains("Einspeis", case=False, na=False)].copy()
    if d_cost.empty:
        return pd.DataFrame(columns=cols)

    cost_sector = (
        d_cost.groupby(["period", "sector"])[["capex", "opex", "co2_cost", "total_cost"]]
        .sum()
        .reset_index()
    )
    load_sector = (
        d_load.groupby(["period", "sector"])["energy_kwh"]
        .sum()
        .reset_index()
    )
    out = cost_sector.merge(load_sector, on=["period", "sector"], how="left")
    out["energy_kwh"] = pd.to_numeric(out["energy_kwh"], errors="coerce").fillna(0.0)
    out["lcoe_eur_per_kwh"] = np.where(out["energy_kwh"] > 0.0, out["total_cost"] / out["energy_kwh"], np.nan)
    out["lcoe_eur_per_mwh"] = out["lcoe_eur_per_kwh"] * 1000.0

    total_rows = []
    for period, g in out.groupby("period"):
        energy_kwh = float(g["energy_kwh"].sum())
        capex = float(g["capex"].sum())
        opex = float(g["opex"].sum())
        co2_cost = float(g["co2_cost"].sum())
        total_cost = float(g["total_cost"].sum())
        total_rows.append({
            "period": str(period),
            "sector": "Gesamt",
            "energy_kwh": energy_kwh,
            "capex": capex,
            "opex": opex,
            "co2_cost": co2_cost,
            "total_cost": total_cost,
            "lcoe_eur_per_kwh": (total_cost / energy_kwh) if energy_kwh > 0.0 else np.nan,
            "lcoe_eur_per_mwh": (total_cost / energy_kwh * 1000.0) if energy_kwh > 0.0 else np.nan,
        })

    if total_rows:
        out = pd.concat([out, pd.DataFrame(total_rows)], ignore_index=True)

    return out[cols]


def build_lcos_df(
    n: pypsa.Network,
    df_cost: pd.DataFrame,
    df_emissions: pd.DataFrame,
    co2_costs_already_in_opex: bool | None = None,
) -> pd.DataFrame:
    """
    Berechnet spezifische Speicherkosten je Speichertechnologie und Periode.
    
    Inputs: n, df_cost, df_emissions, co2_costs_already_in_opex.
    Outputs: DataFrame mit spezifischen Energiekosten je Speichergruppe und Periode.
    """
    cols = [
        "period", "storage_group", "sector", "subcarrier", "energy_kwh",
        "capex", "opex", "co2_cost", "charged_energy_cost", "total_cost",
        "lcos_eur_per_kwh", "lcos_eur_per_mwh",
    ]

    df_total = build_total_cost_df(df_cost, df_emissions, co2_costs_already_in_opex)
    df_energy = build_output_energy_df(n)
    if df_total.empty or df_energy.empty:
        return pd.DataFrame(columns=cols)

    d_cost = df_total.copy()
    d_cost["base_name"] = d_cost["base_name"].astype(str)
    mask_cost = (
        d_cost["component"].astype(str).eq("storage_units")
        | (
            d_cost["component"].astype(str).eq("links")
            & d_cost["base_name"].str.contains(r"_(?:Laden|Entladen)$", case=False, regex=True)
        )
    )
    d_cost = d_cost[mask_cost].copy()
    if d_cost.empty:
        return pd.DataFrame(columns=cols)
    d_cost["storage_group"] = d_cost["base_name"].apply(_storage_group_name)
    cost_grouped = (
        d_cost.groupby(["period", "storage_group"])[["capex", "opex", "co2_cost", "total_cost"]]
        .sum()
        .reset_index()
    )

    df_flow_cost = build_technology_output_cost_df(n, df_cost, df_emissions, co2_costs_already_in_opex)
    if df_flow_cost is None or df_flow_cost.empty:
        charge_cost_grouped = pd.DataFrame(columns=["period", "storage_group", "charged_energy_cost"])
    else:
        charge_cost = df_flow_cost[
            df_flow_cost["component"].astype(str).eq("links")
            & df_flow_cost["base_name"].astype(str).str.contains(r"_Laden$", case=False, regex=True)
        ].copy()
        if charge_cost.empty:
            charge_cost_grouped = pd.DataFrame(columns=["period", "storage_group", "charged_energy_cost"])
        else:
            charge_cost["storage_group"] = charge_cost["base_name"].astype(str).apply(_storage_group_name)
            charge_cost_grouped = (
                charge_cost.groupby(["period", "storage_group"])["input_cost"]
                .sum()
                .reset_index()
                .rename(columns={"input_cost": "charged_energy_cost"})
            )

    d_energy = df_energy.copy()
    d_energy["base_name"] = d_energy["base_name"].astype(str)
    links_discharge = d_energy[
        d_energy["component"].astype(str).eq("links")
        & d_energy["base_name"].str.contains(r"_Entladen$", case=False, regex=True)
    ].copy()
    links_discharge["storage_group"] = links_discharge["base_name"].apply(_storage_group_name)

    su_discharge = d_energy[d_energy["component"].astype(str).eq("storage_units")].copy()
    su_discharge["storage_group"] = su_discharge["base_name"].apply(_storage_group_name)

    link_keys = set(zip(links_discharge["period"].astype(str), links_discharge["storage_group"].astype(str)))
    if link_keys:
        su_discharge = su_discharge[
            ~su_discharge.apply(lambda r: (str(r["period"]), str(r["storage_group"])) in link_keys, axis=1)
        ].copy()

    d_energy = pd.concat([links_discharge, su_discharge], ignore_index=True)
    if d_energy.empty:
        return pd.DataFrame(columns=cols)

    energy_grouped = (
        d_energy.groupby(["period", "storage_group", "sector", "subcarrier"])["energy_kwh"]
        .sum()
        .reset_index()
    )
    out = energy_grouped.merge(cost_grouped, on=["period", "storage_group"], how="left")
    out = out.merge(charge_cost_grouped, on=["period", "storage_group"], how="left")
    for col in ("capex", "opex", "co2_cost", "charged_energy_cost", "total_cost"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out["opex"] = out["opex"] + out["charged_energy_cost"]
    out["total_cost"] = out["total_cost"] + out["charged_energy_cost"]
    out["lcos_eur_per_kwh"] = np.where(out["energy_kwh"] > 0.0, out["total_cost"] / out["energy_kwh"], np.nan)
    out["lcos_eur_per_mwh"] = out["lcos_eur_per_kwh"] * 1000.0
    out = out[out["energy_kwh"] > 0.0].copy()
    return out[cols]


def build_cashflow_df(
    n: pypsa.Network,
    df_inv_capex: pd.DataFrame,
    df_total_cost: pd.DataFrame,
    df_life: pd.DataFrame,
    years: list[int],
) -> pd.DataFrame:
    """
    Rekonstruiert jährliche Kosten- und Cashflow-Reihen aus den Periodendaten.
    
    Inputs: n, df_inv_capex, df_total_cost, df_life, years.
    Outputs: DataFrame mit jährlichen Cashflows.
    """
    cols = [
        "year", "period", "capex_eur", "opex_eur", "co2_cost_eur",
        "net_cashflow_eur", "discount_rate", "discounted_cashflow_eur",
        "cum_cashflow_eur", "cum_discounted_cashflow_eur",
    ]
    if not years:
        return pd.DataFrame(columns=cols)

    years_sorted = sorted(int(y) for y in years)
    end_year = _analysis_horizon_end_year(df_life, years_sorted)
    if end_year is None or end_year < years_sorted[0]:
        return pd.DataFrame(columns=cols)

    rate = _infer_project_discount_rate(n)
    start_year = years_sorted[0]
    co2_in_opex = _co2_costs_already_in_opex_from_df(df_total_cost)

    rows = []
    for year in range(start_year, int(end_year) + 1):
        period = _period_for_year(year, years_sorted)
        capex, opex, co2_cost = _yearly_period_cost_components_for_year(
            df_total_cost=df_total_cost,
            years=years_sorted,
            year=int(year),
        )
        annual_cost = (
            capex + opex
            if co2_in_opex
            else capex + opex + co2_cost
        )
        net = -annual_cost
        discount_factor = (1.0 + rate) ** (year - start_year) if np.isfinite(rate) and rate > -1.0 else 1.0
        discounted = net / discount_factor if discount_factor != 0 else net
        rows.append({
            "year": int(year),
            "period": str(period),
            "capex_eur": capex,
            "opex_eur": opex,
            "co2_cost_eur": co2_cost,
            "net_cashflow_eur": net,
            "discount_rate": rate,
            "discounted_cashflow_eur": discounted,
        })

    out = pd.DataFrame(rows, columns=cols[:-2])
    if out.empty:
        return pd.DataFrame(columns=cols)
    out["cum_cashflow_eur"] = out["net_cashflow_eur"].cumsum()
    out["cum_discounted_cashflow_eur"] = out["discounted_cashflow_eur"].cumsum()
    out.attrs["co2_costs_already_in_opex"] = co2_in_opex
    return out[cols]


def build_variant_delta_cashflow_df(st_base: dict, st_cmp: dict) -> pd.DataFrame:
    """
    Bereitet delta cashflow DataFrame für den Variantenvergleich auf.
    
    Inputs: st_base, st_cmp.
    Outputs: DataFrame mit jährlichen Differenzen zwischen Vergleich- und Basisvariante.
    """
    cols = [
        "year",
        "delta_capex_eur",
        "delta_opex_eur",
        "delta_co2_cost_eur",
        "delta_cashflow_eur",
        "discount_rate",
        "discounted_delta_cashflow_eur",
        "cum_delta_cashflow_eur",
        "cum_discounted_delta_cashflow_eur",
    ]
    df_base = st_base.get("df_cashflow", pd.DataFrame()) if st_base else pd.DataFrame()
    df_cmp = st_cmp.get("df_cashflow", pd.DataFrame()) if st_cmp else pd.DataFrame()
    if df_base is None or df_cmp is None or df_base.empty or df_cmp.empty:
        return pd.DataFrame(columns=cols)

    a = df_base[["year", "capex_eur", "opex_eur", "co2_cost_eur", "net_cashflow_eur"]].copy()
    b = df_cmp[["year", "capex_eur", "opex_eur", "co2_cost_eur", "net_cashflow_eur"]].copy()
    a = a.rename(columns={
        "capex_eur": "capex_base",
        "opex_eur": "opex_base",
        "co2_cost_eur": "co2_base",
        "net_cashflow_eur": "cashflow_base",
    })
    b = b.rename(columns={
        "capex_eur": "capex_cmp",
        "opex_eur": "opex_cmp",
        "co2_cost_eur": "co2_cmp",
        "net_cashflow_eur": "cashflow_cmp",
    })

    out = a.merge(b, on="year", how="outer").fillna(0.0).sort_values("year").reset_index(drop=True)
    out["delta_capex_eur"] = out["capex_cmp"] - out["capex_base"]
    out["delta_opex_eur"] = out["opex_cmp"] - out["opex_base"]
    out["delta_co2_cost_eur"] = out["co2_cmp"] - out["co2_base"]
    out["delta_cashflow_eur"] = out["cashflow_cmp"] - out["cashflow_base"]

    rate = _select_project_discount_rate(
        st_cmp.get("project_discount_rate") if st_cmp else None,
        st_base.get("project_discount_rate") if st_base else None,
        DEFAULT_DISCOUNT_RATE,
    )
    start_year = int(out["year"].min())
    out["discount_rate"] = rate
    out["discounted_delta_cashflow_eur"] = out.apply(
        lambda r: r["delta_cashflow_eur"] / ((1.0 + rate) ** (int(r["year"]) - start_year))
        if np.isfinite(rate) and rate > -1.0 else r["delta_cashflow_eur"],
        axis=1,
    )
    out["cum_delta_cashflow_eur"] = out["delta_cashflow_eur"].cumsum()
    out["cum_discounted_delta_cashflow_eur"] = out["discounted_delta_cashflow_eur"].cumsum()
    return out[cols]


def _npv_from_cashflows(cashflows: list[float], rate: float) -> float:
    """
    Berechnet, wie viel eine Reihe von Zahlungen heute wert ist.
    
    Inputs: cashflows, rate.
    Outputs: Kapitalwert.
    """
    total = 0.0
    for i, cf in enumerate(cashflows):
        total += float(cf) / ((1.0 + float(rate)) ** i)
    return float(total)


def _irr_from_cashflows(cashflows: list[float]) -> float | None:
    """
    Berechnet den internen Zinsfuß, also den Zinssatz, bei dem der Kapitalwert der Cashflows genau 0 wird.
    
    Inputs: cashflows.
    Outputs: Zinssatz als float.
    """
    vals = [float(v) for v in cashflows]
    if not vals or not (any(v > 0 for v in vals) and any(v < 0 for v in vals)):
        return None

    grid = np.concatenate([
        np.linspace(-0.99, 0.5, 300),
        np.linspace(0.5, 5.0, 300),
    ])
    npvs = [_npv_from_cashflows(vals, r) for r in grid]

    left = None
    right = None
    for i in range(len(grid) - 1):
        if np.isnan(npvs[i]) or np.isnan(npvs[i + 1]):
            continue
        if npvs[i] == 0.0:
            return float(grid[i])
        if npvs[i] * npvs[i + 1] < 0.0:
            left = float(grid[i])
            right = float(grid[i + 1])
            break
    if left is None or right is None:
        return None

    for _ in range(120):
        mid = 0.5 * (left + right)
        val_mid = _npv_from_cashflows(vals, mid)
        if abs(val_mid) <= 1e-8:
            return float(mid)
        val_left = _npv_from_cashflows(vals, left)
        if val_left * val_mid <= 0.0:
            right = mid
        else:
            left = mid
    return float(0.5 * (left + right))


def _payback_year(cumulative: pd.Series, years: pd.Series) -> float | None:
    """
    Berechnet das Amortisationsjahr.
    
    Inputs: cumulative, years.
    Outputs: Amortisationsjahr als Zahl.
    """
    if cumulative is None or years is None or cumulative.empty or years.empty:
        return None
    hit = cumulative >= 0.0
    if not bool(hit.any()):
        return None
    idx = int(np.argmax(hit.to_numpy()))
    if idx == 0:
        return float(years.iloc[0])

    prev_val = float(cumulative.iloc[idx - 1])
    curr_val = float(cumulative.iloc[idx])
    prev_year = float(years.iloc[idx - 1])
    curr_year = float(years.iloc[idx])
    if abs(curr_val - prev_val) <= 1e-12:
        return curr_year
    share = (0.0 - prev_val) / (curr_val - prev_val)
    share = max(0.0, min(1.0, share))
    return prev_year + share * (curr_year - prev_year)


def build_variant_financial_summary(st_base: dict, st_cmp: dict) -> dict:
    """
    Berechnet wirtschaftliche Differenzkennzahlen für den Variantenvergleich.
    
    Inputs: st_base, st_cmp.
    Outputs: Dictionary mit wirtschaftlichen Vergleichskennzahlen.
    """
    df_delta = build_variant_delta_cashflow_df(st_base, st_cmp)
    if df_delta.empty:
        return {
            "ok": False,
            "delta_npv_eur": None,
            "irr": None,
            "simple_payback_year": None,
            "discounted_payback_year": None,
            "discount_rate": None,
            "start_year": None,
            "end_year": None,
            "base_start_year": None,
            "comparison_start_year": None,
            "start_year_mismatch": False,
            "df_delta": df_delta,
        }

    rate = float(df_delta["discount_rate"].iloc[0]) if "discount_rate" in df_delta.columns else DEFAULT_DISCOUNT_RATE
    cashflows = df_delta["delta_cashflow_eur"].astype(float).tolist()
    delta_npv = float(df_delta["discounted_delta_cashflow_eur"].sum())
    irr = _irr_from_cashflows(cashflows)
    start_year = int(df_delta["year"].min())
    simple_payback_abs = _payback_year(df_delta["cum_delta_cashflow_eur"], df_delta["year"])
    discounted_payback_abs = _payback_year(df_delta["cum_discounted_delta_cashflow_eur"], df_delta["year"])
    simple_payback = (simple_payback_abs - start_year) if simple_payback_abs is not None else None
    discounted_payback = (discounted_payback_abs - start_year) if discounted_payback_abs is not None else None
    df_base_cash = st_base.get("df_cashflow", pd.DataFrame()) if st_base else pd.DataFrame()
    df_cmp_cash = st_cmp.get("df_cashflow", pd.DataFrame()) if st_cmp else pd.DataFrame()
    base_start_year = int(df_base_cash["year"].min()) if df_base_cash is not None and not df_base_cash.empty and "year" in df_base_cash.columns else None
    comparison_start_year = int(df_cmp_cash["year"].min()) if df_cmp_cash is not None and not df_cmp_cash.empty and "year" in df_cmp_cash.columns else None
    start_year_mismatch = (
        base_start_year is not None
        and comparison_start_year is not None
        and int(base_start_year) != int(comparison_start_year)
    )

    return {
        "ok": True,
        "delta_npv_eur": delta_npv,
        "irr": irr,
        "simple_payback_year": simple_payback,
        "discounted_payback_year": discounted_payback,
        "discount_rate": rate,
        "start_year": start_year,
        "end_year": int(df_delta["year"].max()),
        "base_start_year": base_start_year,
        "comparison_start_year": comparison_start_year,
        "start_year_mismatch": start_year_mismatch,
        "df_delta": df_delta,
    }


def build_lcoe_technology_fig(
    df_lcoe: pd.DataFrame,
    period_value: str | None,
    max_components: int = 25,
    years: list[int] | None = None,
) -> go.Figure:
    """
    Berechnet oder formatiert die Abbildung der Stromgestehungskosten je Technologie.
    
    Inputs: df_lcoe, period_value, max_components, years.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_lcoe is None or df_lcoe.empty:
        fig.update_layout(title="Stromgestehungskosten (LCOE) je Technologie (keine Daten)")
        return fig

    d = df_lcoe.copy()
    d = d[d["sector"].astype(str).eq("Strom")].copy()
    # Speicher separat über LCOS auswerten, damit sie das LCOE-Technologiediagramm nicht verzerren.
    storage_mask = d["label"].astype(str).str.contains(
        r"(?:^storage_units__|Speicher|_Entladen|_Laden)",
        case=False,
        regex=True,
    )
    export_mask = d["label"].astype(str).str.contains(
        r"(?:Exportleitung|Einspeis)",
        case=False,
        regex=True,
    )
    transfer_mask = d["label"].astype(str).str.contains(
        r"(?:Stromnutzung|Quartiersleitung|Stromleitung)",
        case=False,
        regex=True,
    )
    d = d[~storage_mask & ~export_mask & ~transfer_mask].copy()
    if period_value not in (None, "", "Alle"):
        d = d[d["period"].astype(str) == str(period_value)]
    if d.empty:
        fig.update_layout(title="Stromgestehungskosten (LCOE) je Technologie (keine Daten)")
        return fig

    if period_value in (None, "", "Alle"):
        order = [str(y) for y in years] if years else sorted(d["period"].astype(str).unique().tolist()) or ["Single"]
        g = (
            d.groupby(["period", "label"])[["energy_kwh", "total_cost"]]
            .sum()
            .reset_index()
        )
        g["lcoe_ct_per_kwh"] = np.where(g["energy_kwh"] > 0.0, g["total_cost"] / g["energy_kwh"] * 100.0, np.nan)
        g = g.replace([np.inf, -np.inf], np.nan).dropna(subset=["lcoe_ct_per_kwh"])
        if g.empty:
            fig.update_layout(title="Stromgestehungskosten (LCOE) je Technologie (keine Daten)")
            return fig

        totals = g.groupby("label")["total_cost"].sum().sort_values(ascending=False)
        if max_components is not None and len(totals) > max_components:
            keep = set(totals.head(max_components).index.tolist())
            g = g[g["label"].isin(keep)].copy()
            totals = totals.head(max_components)

        labels = totals.index.tolist()
        name_map = display_name_map(labels)
        palette = px.colors.qualitative.Vivid + px.colors.qualitative.Bold
        for idx, label in enumerate(labels):
            s = g[g["label"].astype(str) == str(label)].set_index("period")["lcoe_ct_per_kwh"].reindex(order)
            if s.dropna().empty:
                continue
            fig.add_trace(go.Bar(
                name=name_map.get(label, label),
                x=order,
                y=s.fillna(0.0).values,
                marker=dict(color=palette[idx % len(palette)]),
                hovertemplate=f"%{{x}}<br>{name_map.get(label, label)}: %{{y:.2f}} ct/kWh<extra></extra>",
            ))

        fig.update_layout(
            title="Stromgestehungskosten (LCOE) je Technologie und Investitionsperiode",
            barmode="group",
            xaxis_title="Investitionsperiode",
            yaxis_title="Stromgestehungskosten [ct/kWh]",
            margin=dict(l=30, r=30, t=60, b=80),
            legend_title="Technologie",
        )
        return fig

    g = (
        d.groupby("label")[["energy_kwh", "total_cost"]]
        .sum()
        .reset_index()
    )
    g["lcoe_ct_per_kwh"] = np.where(g["energy_kwh"] > 0.0, g["total_cost"] / g["energy_kwh"] * 100.0, np.nan)
    g = g.replace([np.inf, -np.inf], np.nan).dropna(subset=["lcoe_ct_per_kwh"])
    if g.empty:
        fig.update_layout(title="Stromgestehungskosten (LCOE) je Technologie (keine Daten)")
        return fig

    totals = g.groupby("label")["total_cost"].sum().sort_values(ascending=False)
    if max_components is not None and len(totals) > max_components:
        keep = set(totals.head(max_components).index.tolist())
        g = g[g["label"].isin(keep)].copy()
        totals = totals.head(max_components)

    labels = totals.index.tolist()
    name_map = display_name_map(labels)
    x = [name_map.get(label, label) for label in labels]

    s = g.set_index("label")["lcoe_ct_per_kwh"]
    y = [float(s.get(label, np.nan)) if np.isfinite(float(s.get(label, np.nan))) else np.nan for label in labels]
    fig.add_trace(go.Bar(
        name="Strom",
        x=x,
        y=y,
        marker=dict(color=px.colors.qualitative.Vivid[0] if len(px.colors.qualitative.Vivid) > 0 else "#1f77b4"),
        hovertemplate="%{x}<br>Stromgestehungskosten: %{y:.2f} ct/kWh<extra></extra>",
    ))

    period_txt = str(period_value) if period_value not in (None, "", "Alle") else "alle Perioden"
    fig.update_layout(
        title=f"Stromgestehungskosten (LCOE) je Technologie - {period_txt}",
        barmode="group",
        xaxis_title="Technologie",
        yaxis_title="Stromgestehungskosten [ct/kWh]",
        margin=dict(l=30, r=30, t=60, b=140),
        showlegend=False,
    )
    fig.update_xaxes(tickangle=45)
    return fig

# Reihenfolge Wärmeerzeugungstechnologien im Dashboard
HEAT_GENERATION_TECH_ORDER = ["Fernwärme", "Wärmepumpe", "Gaskessel", "BHKW"]


def _heat_generation_technology(label: str) -> str | None:
    """
    Erkennt aus den Komponentenlabeln, ob es sich um eine Wärmeerzeugungstechnologie handelt.
    
    Inputs: label.
    Outputs: Name der Wärmeerzeugungstechnologie.
    """
    text = strip_variable_suffix(strip_prefix(str(label)))
    if "Fernwärme" in text or "Fernwaerme" in text:
        return "Fernwärme"
    if "Wärmepumpe" in text or "Waermepumpe" in text:
        return "Wärmepumpe"
    if "Gaskessel" in text:
        return "Gaskessel"
    if "BHKW" in text and "Stromnutzung" not in text and "Exportleitung" not in text:
        return "BHKW"
    return None


def build_heat_generation_cost_fig(
    df_lcoe: pd.DataFrame,
    period_value: str | None,
    max_components: int = 25,
    years: list[int] | None = None,
) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für Wärmegestehungskosten je Technologie.
    
    Inputs: df_lcoe, period_value, max_components, years.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_lcoe is None or df_lcoe.empty:
        fig.update_layout(title="Wärmegestehungskosten (LCOH) je Technologie (keine Daten)")
        return fig

    d = df_lcoe.copy()
    d = d[d["sector"].astype(str).eq("Wärme")].copy()
    storage_mask = d["label"].astype(str).str.contains(
        r"(?:^storage_units__|Speicher|_Entladen|_Laden)",
        case=False,
        regex=True,
    )
    d = d[~storage_mask].copy()
    d["heat_technology"] = d["label"].astype(str).apply(_heat_generation_technology)
    d = d[d["heat_technology"].notna()].copy()
    if period_value not in (None, "", "Alle"):
        d = d[d["period"].astype(str) == str(period_value)]
    if d.empty:
        fig.update_layout(title="Wärmegestehungskosten (LCOH) je Technologie (keine Daten)")
        return fig

    if period_value in (None, "", "Alle"):
        order = [str(y) for y in years] if years else sorted(d["period"].astype(str).unique().tolist()) or ["Single"]
        g = (
            d.groupby(["period", "heat_technology"])[["energy_kwh", "total_cost"]]
            .sum()
            .reset_index()
        )
        g["cost_ct_per_kwh"] = np.where(g["energy_kwh"] > 0.0, g["total_cost"] / g["energy_kwh"] * 100.0, np.nan)
        g = g.replace([np.inf, -np.inf], np.nan).dropna(subset=["cost_ct_per_kwh"])
        if g.empty:
            fig.update_layout(title="Wärmegestehungskosten (LCOH) je Technologie (keine Daten)")
            return fig

        totals = g.groupby("heat_technology")["total_cost"].sum()
        present = set(totals.index.tolist())
        labels = [tech for tech in HEAT_GENERATION_TECH_ORDER if tech in present]
        labels += [tech for tech in sorted(present) if tech not in labels]
        if max_components is not None and len(labels) > max_components:
            labels = labels[:max_components]
            g = g[g["heat_technology"].isin(labels)].copy()

        palette = px.colors.qualitative.Vivid + px.colors.qualitative.Bold
        for idx, label in enumerate(labels):
            s = g[g["heat_technology"].astype(str) == str(label)].set_index("period")["cost_ct_per_kwh"].reindex(order)
            if s.dropna().empty:
                continue
            fig.add_trace(go.Bar(
                name=str(label),
                x=order,
                y=s.fillna(0.0).values,
                marker=dict(color=palette[idx % len(palette)]),
                hovertemplate=f"%{{x}}<br>{label}: %{{y:.2f}} ct/kWh<extra></extra>",
            ))

        fig.update_layout(
            title="Wärmegestehungskosten (LCOH) je Technologie und Investitionsperiode",
            barmode="group",
            xaxis_title="Investitionsperiode",
            yaxis_title="Wärmegestehungskosten [ct/kWh]",
            margin=dict(l=30, r=30, t=60, b=80),
            legend_title="Technologie",
        )
        return fig

    g = (
        d.groupby("heat_technology")[["energy_kwh", "total_cost"]]
        .sum()
        .reset_index()
    )
    g["cost_ct_per_kwh"] = np.where(g["energy_kwh"] > 0.0, g["total_cost"] / g["energy_kwh"] * 100.0, np.nan)
    g = g.replace([np.inf, -np.inf], np.nan).dropna(subset=["cost_ct_per_kwh"])
    if g.empty:
        fig.update_layout(title="Wärmegestehungskosten (LCOH) je Technologie (keine Daten)")
        return fig

    totals = g.groupby("heat_technology")["total_cost"].sum()
    if max_components is not None and len(totals) > max_components:
        keep = set(totals.head(max_components).index.tolist())
        g = g[g["heat_technology"].isin(keep)].copy()
        totals = totals.head(max_components)

    present = set(totals.index.tolist())
    labels = [tech for tech in HEAT_GENERATION_TECH_ORDER if tech in present]
    labels += [tech for tech in sorted(present) if tech not in labels]
    x = labels
    s = g.set_index("heat_technology")["cost_ct_per_kwh"]
    y = [float(s.get(label, np.nan)) if np.isfinite(float(s.get(label, np.nan))) else np.nan for label in labels]
    fig.add_trace(go.Bar(
        name="Wärme",
        x=x,
        y=y,
        marker=dict(color=px.colors.qualitative.Vivid[1] if len(px.colors.qualitative.Vivid) > 1 else "#ff7f0e"),
        hovertemplate="%{x}<br>Wärmegestehungskosten: %{y:.2f} ct/kWh<extra></extra>",
    ))

    period_txt = str(period_value) if period_value not in (None, "", "Alle") else "alle Perioden"
    fig.update_layout(
        title=f"Wärmegestehungskosten (LCOH) je Technologie - {period_txt}",
        barmode="group",
        xaxis_title="Technologie",
        yaxis_title="Wärmegestehungskosten [ct/kWh]",
        margin=dict(l=30, r=30, t=60, b=140),
        showlegend=False,
    )
    fig.update_xaxes(tickangle=45)
    return fig


def build_specific_storage_cost_fig(
    df_lcos: pd.DataFrame,
    years: list[int],
    period_value: str | None = "Alle",
) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für spezifische Speicherkosten.
    
    Inputs: df_lcos, years, period_value.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    title_empty = "Spezifische Speicherkosten (LCOS) (keine Daten)"
    if df_lcos is None or df_lcos.empty:
        fig.update_layout(title=title_empty)
        return fig

    d = df_lcos.copy()
    if period_value not in (None, "", "Alle"):
        d = d[d["period"].astype(str) == str(period_value)]
    if d.empty:
        fig.update_layout(title=title_empty)
        return fig

    if period_value in (None, "", "Alle"):
        order = [str(y) for y in years] if years else sorted(d["period"].astype(str).unique().tolist()) or ["Single"]
        g = (
            d.groupby(["period", "storage_group"])[["energy_kwh", "total_cost"]]
            .sum()
            .reset_index()
        )
        g["lcos_ct_per_kwh"] = np.where(g["energy_kwh"] > 0.0, g["total_cost"] / g["energy_kwh"] * 100.0, np.nan)
        g = g.replace([np.inf, -np.inf], np.nan).dropna(subset=["lcos_ct_per_kwh"])
        if g.empty:
            fig.update_layout(title=title_empty)
            return fig
        groups = g.groupby("storage_group")["total_cost"].sum().sort_values(ascending=False).index.tolist()
        palette = px.colors.qualitative.Vivid + px.colors.qualitative.Bold
        for idx, group in enumerate(groups):
            s = g[g["storage_group"].astype(str) == str(group)].set_index("period")["lcos_ct_per_kwh"].reindex(order)
            if s.dropna().empty:
                continue
            fig.add_trace(go.Bar(
                name=str(group),
                x=order,
                y=s.fillna(0.0).values,
                marker=dict(color=palette[idx % len(palette)]),
                hovertemplate=f"%{{x}}<br>{group}: %{{y:.2f}} ct/kWh<extra></extra>",
            ))
        fig.update_layout(
            title="Spezifische Speicherkosten (LCOS) je Investitionsperiode",
            barmode="group",
            xaxis_title="Investitionsperiode",
            yaxis_title="LCOS [ct/kWh]",
            margin=dict(l=30, r=30, t=60, b=80),
            legend_title="Speicher",
        )
        return fig

    g = (
        d.groupby("storage_group")[["energy_kwh", "total_cost"]]
        .sum()
        .reset_index()
    )
    g["lcos_ct_per_kwh"] = np.where(g["energy_kwh"] > 0.0, g["total_cost"] / g["energy_kwh"] * 100.0, np.nan)
    g = g.replace([np.inf, -np.inf], np.nan).dropna(subset=["lcos_ct_per_kwh"])
    if g.empty:
        fig.update_layout(title=title_empty)
        return fig
    g = g.sort_values("total_cost", ascending=False)
    fig.add_trace(go.Bar(
        name="Spezifische Speicherkosten (LCOS)",
        x=g["storage_group"].astype(str).tolist(),
        y=g["lcos_ct_per_kwh"].astype(float).tolist(),
        marker=dict(color=COST_COLOR_MAP.get("OPEX")),
        hovertemplate="%{x}<br>%{y:.2f} ct/kWh<extra></extra>",
    ))
    fig.update_layout(
        title=f"Spezifische Speicherkosten (LCOS) - {period_value}",
        xaxis_title="Speicher",
        yaxis_title="LCOS [ct/kWh]",
        margin=dict(l=30, r=30, t=60, b=80),
        showlegend=False,
    )
    return fig


def build_cashflow_fig(df_cashflow: pd.DataFrame) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für die jährliche Kostenentwicklung.
    
    Inputs: df_cashflow.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_cashflow is None or df_cashflow.empty:
        fig.update_layout(title="Jährliche Kostenentwicklung (keine Daten)")
        return fig

    x = df_cashflow["year"].astype(int).tolist()
    fig.add_trace(go.Bar(
        name="CAPEX (Annuität)",
        x=x,
        y=df_cashflow["capex_eur"].values,
        marker=dict(color=COST_COLOR_MAP.get("CAPEX")),
        hovertemplate="%{x}<br>CAPEX (Annuität): %{y:.2f} EUR<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="OPEX",
        x=x,
        y=(
            df_cashflow["opex_eur"].fillna(0.0)
            if _co2_costs_already_in_opex_from_df(df_cashflow)
            else df_cashflow["opex_eur"].fillna(0.0) + df_cashflow["co2_cost_eur"].fillna(0.0)
        ).values,
        marker=dict(color=COST_COLOR_MAP.get("OPEX")),
        hovertemplate="%{x}<br>OPEX: %{y:.2f} EUR<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="Aufsummierte abgezinste Kosten",
        x=x,
        y=(-df_cashflow["cum_discounted_cashflow_eur"]).values,
        mode="lines+markers",
        yaxis="y2",
        line=dict(color=COST_COLOR_MAP.get("Kumuliert"), width=3),
        hovertemplate="%{x}<br>Aufsummierte abgezinste Kosten: %{y:.2f} EUR<extra></extra>",
    ))
    fig.update_layout(
        title="Jährliche Kostenentwicklung (CAPEX = Investitionskosten als Annuität; OPEX = Betriebskosten)",
        barmode="relative",
        xaxis_title="Jahr",
        yaxis_title="Jährliche Kosten / Erlöse [EUR]",
        yaxis2=dict(
            title="Aufsummierte abgezinste Kosten [EUR]",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        margin=dict(l=125, r=170, t=145, b=76),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="left", x=0),
        legend_title_text="",
    )
    return fig


def build_variant_delta_cashflow_fig(df_delta: pd.DataFrame) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für die jährliche Kostenvorteil / -nachteil der Vergleichsvariante gegenüber der Datenbasis.
    
    Inputs: df_delta.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_delta is None or df_delta.empty:
        fig.update_layout(title="Jährlicher Kostenvorteil / -nachteil der Vergleichsvariante gegenüber der Datenbasis (keine Daten)")
        return fig

    x = df_delta["year"].astype(int).tolist()
    values = pd.to_numeric(df_delta["delta_cashflow_eur"], errors="coerce").fillna(0.0)
    fig.add_trace(go.Bar(
        name="Jährlicher Kostenvorteil / -nachteil",
        x=x,
        y=values.values,
        marker=dict(color=[
            COST_COLOR_MAP.get("Vorteil") if float(v) >= 0.0 else COST_COLOR_MAP.get("Nachteil")
            for v in values.values
        ]),
        customdata=np.array([
            "Jährlicher Kostenvorteil" if float(v) >= 0.0 else "Jährlicher Kostennachteil"
            for v in values.values
        ], dtype=object),
        showlegend=False,
        hovertemplate="%{x}<br>%{customdata}: %{y:.2f} EUR<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="Jährlicher Kostenvorteil",
        x=[None],
        y=[None],
        mode="markers",
        marker=dict(color=COST_COLOR_MAP.get("Vorteil"), size=12, symbol="square"),
        hoverinfo="skip",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        name="Jährlicher Kostennachteil",
        x=[None],
        y=[None],
        mode="markers",
        marker=dict(color=COST_COLOR_MAP.get("Nachteil"), size=12, symbol="square"),
        hoverinfo="skip",
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        name="Aufsummierter abgezinster Kostenvorteil / -nachteil",
        x=x,
        y=df_delta["cum_discounted_delta_cashflow_eur"].values,
        mode="lines+markers",
        yaxis="y2",
        line=dict(color=COST_COLOR_MAP.get("Kumuliert"), width=3),
        hovertemplate="%{x}<br>Aufsummierter abgezinster Kostenvorteil / -nachteil: %{y:.2f} EUR<extra></extra>",
    ))
    fig.update_layout(
        title="Jährlicher Kostenvorteil / -nachteil der Vergleichsvariante gegenüber der Datenbasis",
        xaxis_title="Jahr",
        yaxis_title="Jährlicher Kostenvorteil / -nachteil [EUR]",
        yaxis2=dict(
            title="Aufsummierter abgezinster Kostenvorteil / -nachteil [EUR]",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        margin=dict(l=125, r=170, t=145, b=76),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="left", x=0),
        legend_title_text="",
    )
    fig.add_hline(y=0.0, line_dash="dash", line_color="#999")
    return fig


def build_variant_financial_summary_fig(summary: dict) -> go.Figure:
    """
    Bereitet Dashboard-Tabelle für den Variantenvergleich auf.
    Wirtschaftliche Kennzahlen der Tabelle: Kapitalwertdifferenz, interner Zinsfuß, Amortisationszeit ohne Abzinsung, Amortisationszeit mit Abzinsung,
    Kalkulationszins, Betrachtungszeitraum
    
    Inputs: summary.
    Outputs: Plotly-Tabelle.
    """
    fig = go.Figure()
    if not summary or not summary.get("ok", False):
        fig.update_layout(title="Wirtschaftliche Differenzkennzahlen der Vergleichsvariante gegenüber der Datenbasis (keine Daten)")
        return fig

    def _fmt_money(v):
        return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{float(v):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")

    def _fmt_rate(v):
        return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{format_number_de(100.0 * float(v), 2)} %"


    def _fmt_payback(v, discounted: bool = False):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            if discounted:
                return "Keine Amortisation im Betrachtungszeitraum"
            return "Keine Amortisation im Betrachtungszeitraum"
        return f"{format_number_de(float(v), 2)} a"

    labels = [
        "Kapitalwertdifferenz (Delta-NPV)",
        "Interner Zinsfuß (IRR)",
        "Amortisationszeit ohne Abzinsung",
        "Amortisationszeit mit Abzinsung",
        "Kalkulationszins",
        "Betrachtungszeitraum",
    ]
    period_value = (
        f"{summary.get('start_year')} - {summary.get('end_year')}"
        if summary.get("start_year") is not None and summary.get("end_year") is not None
        else "n/a"
    )
    if summary.get("start_year_mismatch", False):
        period_value = (
            "Unterschiedliche Startjahre "
            f"(Basis: {summary.get('base_start_year')}, Vergleich: {summary.get('comparison_start_year')})"
        )
    values = [
        _fmt_money(summary.get("delta_npv_eur")),
        _fmt_rate(summary.get("irr")),
        _fmt_payback(summary.get("simple_payback_year"), discounted=False),
        _fmt_payback(summary.get("discounted_payback_year"), discounted=True),
        _fmt_rate(summary.get("discount_rate")),
        period_value,
    ]

    row_height = 44
    fig_height = max(460, 120 + row_height * (len(labels) + 1))
    fig.add_trace(go.Table(
        columnwidth=[2.05, 2.55],
        header=dict(
            values=["<b>Kennzahl</b>", "<b>Wert</b>"],
            fill_color="#f2f4f8",
            align="left",
            height=46,
            font=dict(size=15, color="#1f3555"),
        ),
        cells=dict(
            values=[labels, values],
            align="left",
            height=row_height,
            font=dict(size=14, color="#1f3555"),
        ),
    ))
    fig.update_layout(
        title="Wirtschaftliche Differenzkennzahlen der Vergleichsvariante gegenüber der Datenbasis",
        height=fig_height,
        margin=dict(l=20, r=20, t=82, b=24),
    )
    return fig


def build_total_cost_period_fig(df_total_cost: pd.DataFrame, years: list[int]) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für Gesamtkosten je Investitionsperiode.
    
    Inputs: df_total_cost, years.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_total_cost is None or df_total_cost.empty:
        fig.update_layout(title="Gesamtkosten je Investitionsperiode (keine Daten)")
        return fig

    d_cost = _with_opex_including_co2(df_total_cost)
    cols = ["capex", "opex_incl_co2"]
    if years:
        order = [str(y) for y in years]
        agg = d_cost.groupby("period")[cols].sum().reindex(order).fillna(0.0)
    else:
        agg = d_cost.groupby("period")[cols].sum().fillna(0.0)

    x = agg.index.tolist()
    fig.add_trace(go.Bar(
        name="CAPEX",
        x=x,
        y=agg["capex"].values if "capex" in agg.columns else np.zeros(len(x)),
        marker=dict(color=COST_COLOR_MAP.get("CAPEX")),
        hovertemplate=f"%{{x}}<br>CAPEX: %{{y:.2f}} {COST_UNIT}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="OPEX",
        x=x,
        y=agg["opex_incl_co2"].values if "opex_incl_co2" in agg.columns else np.zeros(len(x)),
        marker=dict(color=COST_COLOR_MAP.get("OPEX")),
        hovertemplate=f"%{{x}}<br>OPEX: %{{y:.2f}} {COST_UNIT}<extra></extra>",
    ))

    fig.update_layout(
        title="Gesamtkosten je Investitionsperiode (CAPEX als Annuität + OPEX)",
        barmode="stack",
        xaxis_title="Investitionsperiode",
        yaxis_title=f"Kosten [{COST_UNIT}]",
        margin=dict(l=30, r=30, t=60, b=50),
        legend_title="Kostenart",
    )
    return fig


def build_total_cost_singleyear_fig(df_total_cost: pd.DataFrame, period_label: str = "Single") -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für Gesamtkosten.
    
    Inputs: df_total_cost, period_label.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_total_cost is None or df_total_cost.empty:
        fig.update_layout(title="Gesamtkosten (keine Daten)")
        return fig

    d_all = _with_opex_including_co2(df_total_cost)
    d = d_all[d_all["period"].astype(str) == str(period_label)].copy()
    vals = {
        "CAPEX": float(d["capex"].sum()) if "capex" in d.columns else 0.0,
        "OPEX": float(d["opex_incl_co2"].sum()) if "opex_incl_co2" in d.columns else 0.0,
    }
    colors = {
        "CAPEX": COST_COLOR_MAP.get("CAPEX"),
        "OPEX": COST_COLOR_MAP.get("OPEX"),
    }
    for name, value in vals.items():
        fig.add_trace(go.Bar(
            name=name,
            x=[name],
            y=[value],
            marker=dict(color=colors.get(name)),
            hovertemplate=name + f"<br>%{{y:.2f}} {COST_UNIT}<extra></extra>",
        ))

    fig.update_layout(
        title="Gesamtkosten (Einjahresanalyse: CAPEX als Annuität + OPEX)",
        barmode="group",
        xaxis_title="Kostenart",
        yaxis_title=f"Kosten [{COST_UNIT}]",
        margin=dict(l=30, r=30, t=60, b=50),
        legend_title="Kostenart",
    )
    return fig


def build_total_cost_component_fig(df_total_cost: pd.DataFrame, max_components: int | None = 30) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für Gesamtkosten nach Komponenten.
    
    Inputs: df_total_cost, max_components.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_total_cost is None or df_total_cost.empty:
        fig.update_layout(title="Gesamtkosten nach Komponenten (keine Daten)")
        return fig

    d_cost = _with_opex_including_co2(df_total_cost)
    g = d_cost.groupby("label")[["capex", "opex_incl_co2"]].sum()
    g["total"] = g["capex"] + g["opex_incl_co2"]
    g = g[g["total"].abs() > CHART_EPS].copy()
    if g.empty:
        return empty_info_figure(
            "Gesamtkosten nach Komponenten",
            "Für die aktuelle Auswahl liegen keine Komponenten mit Kosten ungleich 0 vor.",
        )
    g = g.sort_values("total", ascending=False)
    if max_components is not None and len(g) > max_components:
        g = g.head(max_components)

    labels = g.index.tolist()
    name_map = display_name_map(labels)
    x = [name_map.get(l, l) for l in labels]

    fig.add_trace(go.Bar(
        name="CAPEX",
        x=x,
        y=g["capex"].values,
        marker=dict(color=COST_COLOR_MAP.get("CAPEX")),
    ))
    fig.add_trace(go.Bar(
        name="OPEX",
        x=x,
        y=g["opex_incl_co2"].values,
        marker=dict(color=COST_COLOR_MAP.get("OPEX")),
    ))

    fig.update_layout(
        title="Gesamtkosten nach Komponenten, negative Kosten sind Erlöse",
        barmode="stack",
        xaxis_title="Komponente",
        yaxis_title=f"Kosten [{COST_UNIT}]",
        margin=dict(l=30, r=30, t=60, b=120),
        legend_title="Kostenart",
    )
    fig.update_xaxes(tickangle=45)
    return fig



def build_total_cost_type_pie_fig(
    df_total_cost: pd.DataFrame,
    df_inv_capex: pd.DataFrame | None = None,
    years: list[int] | None = None,
    period_value: str | None = None,
    df_cashflow: pd.DataFrame | None = None,
) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für Gesamtkostenstruktur nach Kostenart.
    
    Inputs: df_total_cost, df_inv_capex, years, period_value, df_cashflow.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_total_cost is None or df_total_cost.empty:
        fig.update_layout(title="Gesamtkostenstruktur nach Kostenart (keine Daten)")
        return fig

    d = _with_opex_including_co2(df_total_cost)
    if period_value not in (None, "", "Alle"):
        d = d[d["period"].astype(str) == str(period_value)].copy()
    elif years:
        d = d[d["period"].astype(str).isin([str(y) for y in years])].copy()
    if d.empty:
        fig.update_layout(title="Gesamtkostenstruktur nach Kostenart (keine Daten)")
        return fig

    cf_period = pd.DataFrame()
    if df_cashflow is not None and not df_cashflow.empty:
        cf_period = df_cashflow.copy()
        if period_value not in (None, "", "Alle"):
            cf_period = cf_period[cf_period["period"].astype(str) == str(period_value)].copy()
        elif years:
            cf_period = cf_period[cf_period["period"].astype(str).isin([str(y) for y in years])].copy()
        for col in ("capex_eur", "opex_eur", "co2_cost_eur"):
            if col not in cf_period.columns:
                cf_period[col] = 0.0
            cf_period[col] = pd.to_numeric(cf_period[col], errors="coerce").fillna(0.0)

    capex_value = None
    if not cf_period.empty:
        capex_value = float(cf_period["capex_eur"].sum())
    elif df_inv_capex is not None and not df_inv_capex.empty:
        inv = df_inv_capex.copy()
        if period_value not in (None, "", "Alle"):
            inv = inv[inv["period"].astype(str) == str(period_value)].copy()
        elif years:
            inv = inv[inv["period"].astype(str).isin([str(y) for y in years])].copy()
        capex_value = float(pd.to_numeric(inv.get("investment_capex", 0.0), errors="coerce").fillna(0.0).sum()) if not inv.empty else 0.0
    if capex_value is None:
        capex_value = float(d["capex"].sum())

    opex_value = None
    if not cf_period.empty:
        co2_in_opex = _co2_costs_already_in_opex_from_df(df_total_cost)
        opex_value = float(
            cf_period["opex_eur"].sum()
            if co2_in_opex
            else cf_period["opex_eur"].sum() + cf_period["co2_cost_eur"].sum()
        )
    if opex_value is None:
        opex_value = float(d["opex_incl_co2"].sum())

    labels = ["CAPEX", "OPEX"]
    values = [max(0.0, capex_value), max(0.0, opex_value)]
    if sum(values) <= 0.0:
        return empty_info_figure(
            "Gesamtkostenstruktur nach Kostenart",
            "Für die aktuelle Auswahl liegen keine positiven CAPEX- oder OPEX-Werte vor.",
        )
    fig.add_trace(go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=[COST_COLOR_MAP.get("CAPEX"), COST_COLOR_MAP.get("OPEX")]),
        hole=0.35,
        hovertemplate="%{label}<br>%{value:.2f} EUR/Periode<br>%{percent}<extra></extra>",
    ))
    period_txt = (
        str(period_value)
        if period_value not in (None, "", "Alle")
        else ("alle Investitionsperioden" if years else "Single")
    )
    fig.update_layout(
        title=f"Gesamtkostenstruktur je Investitionsperiode: CAPEX und OPEX ({period_txt})",
        margin=dict(l=30, r=30, t=60, b=40),
        legend_title="Kostenart",
    )
    return fig


def build_total_cost_comparison_fig(
    df_total_cost: pd.DataFrame,
    base_period: str,
    selected_period: str,
    max_components: int | None = 30,
) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für Gesamtkostenverteilung.
    
    Inputs: df_total_cost, base_period, selected_period, max_components.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    if df_total_cost is None or df_total_cost.empty:
        fig.update_layout(title="Gesamtkostenverteilung (keine Daten)")
        return fig

    d = _with_opex_including_co2(df_total_cost)
    d = d[d["period"].isin([base_period, selected_period])].copy()
    if d.empty:
        fig.update_layout(title="Gesamtkostenverteilung (keine Daten)")
        return fig

    g = d.groupby(["period", "label"])[["capex", "opex_incl_co2"]].sum().reset_index()
    g["total"] = g["capex"] + g["opex_incl_co2"]
    label_totals = g.groupby("label")["total"].sum()
    labels_with_values = set(label_totals[label_totals.abs() > CHART_EPS].index.tolist())
    g = g[g["label"].isin(labels_with_values)].copy()
    if g.empty:
        return empty_info_figure(
            "Gesamtkostenverteilung",
            "Für die aktuelle Auswahl liegen keine Komponenten mit Kosten ungleich 0 vor.",
        )

    sel = g[g["period"] == selected_period].set_index("label")["total"]
    if sel.empty:
        sel = g.set_index("label")["total"]
    sel = sel.sort_values(ascending=False)
    if max_components is not None and len(sel) > max_components:
        keep = set(sel.head(max_components).index.tolist())
        g = g[g["label"].isin(keep)].copy()
        sel = sel.head(max_components)

    labels = [l for l in sel.index.tolist() if l in set(g["label"])]
    name_map = display_name_map(labels)
    x = [name_map.get(l, l) for l in labels]

    def _vals(period: str, col: str) -> list[float]:
        s = g[g["period"] == period].set_index("label")[col]
        return [float(s.get(l, 0.0)) for l in labels]

    for name, color in [
        ("CAPEX", COST_COLOR_MAP.get("CAPEX")),
        ("OPEX", COST_COLOR_MAP.get("OPEX")),
    ]:
        col = "opex_incl_co2" if name == "OPEX" else name.lower()
        if col not in g.columns:
            continue
        fig.add_trace(go.Bar(
            x=x,
            y=_vals(base_period, col),
            name=name,
            legendgroup=name,
            showlegend=True,
            offsetgroup="Base",
            marker=dict(color=color, opacity=0.55, pattern=dict(shape="/")) if color else dict(opacity=0.55, pattern=dict(shape="/")),
            hovertemplate=f"Datenbasis ({base_period})<br>%{{x}}<br>%{{y:.2f}} {COST_UNIT}<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            x=x,
            y=_vals(selected_period, col),
            name=name,
            legendgroup=name,
            showlegend=False,
            offsetgroup="Selected",
            marker=dict(color=color, opacity=1.0) if color else dict(opacity=1.0),
            hovertemplate=f"Vergleich ({selected_period})<br>%{{x}}<br>%{{y:.2f}} {COST_UNIT}<extra></extra>",
        ))

    fig.update_layout(
        title=f"Gesamtkostenverteilung: Datenbasis ({base_period}) und Vergleich ({selected_period})",
        barmode="relative",
        xaxis_title="Komponente",
        yaxis_title=f"Kosten [{COST_UNIT}]",
        margin=dict(l=30, r=30, t=60, b=140),
        legend_title="Kostenart",
        legend=dict(groupclick="togglegroup"),
    )
    fig.update_xaxes(tickangle=45)
    return fig


def _total_system_cost_with_co2_for_period(df_total_cost: pd.DataFrame, period: str) -> float:
    """
    Berechnet die gesamten Systemkosten in einer bestimmten Periode.
    
    Inputs: df_total_cost, period.
    Outputs: Gesamtsystemkosten dieser Periode inklusive CO₂-Kosten.
    """
    if df_total_cost is None or df_total_cost.empty:
        return 0.0
    d = df_total_cost[df_total_cost["period"].astype(str) == str(period)].copy()
    if d.empty:
        return 0.0
    return float(d["total_cost"].sum()) if "total_cost" in d.columns else float(
        d.get("capex", 0.0).sum()
        + d.get("opex", 0.0).sum()
        + (0.0 if _co2_costs_already_in_opex_from_df(df_total_cost) else d.get("co2_cost", 0.0).sum())
    )


def build_variant_total_cost_compare_fig(
    st_base: dict,
    st_cmp: dict,
    base_name: str,
    cmp_name: str,
    period_cost: str,
) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für Gesamtkosten der Basisvariante und der Vergleichsvariante in einer bestimmten Periode.
    
    Inputs: st_base, st_cmp, base_name, cmp_name, period_cost.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    df_a = st_base.get("df_total_cost", pd.DataFrame()) if st_base else pd.DataFrame()
    df_b = st_cmp.get("df_total_cost", pd.DataFrame()) if st_cmp else pd.DataFrame()
    period_a = _resolve_df_period(df_a, period_cost)
    period_b = _resolve_df_period(df_b, period_cost)

    def _vals(df: pd.DataFrame, period: str) -> tuple[float, float, float]:
        if df is None or df.empty:
            return 0.0, 0.0, 0.0
        if period is None:
            return 0.0, 0.0, 0.0
        d = df[df["period"].astype(str) == str(period)].copy()
        if d.empty:
            return 0.0, 0.0, 0.0
        return (
            float(d["capex"].sum()) if "capex" in d.columns else 0.0,
            float(d["opex"].sum()) if "opex" in d.columns else 0.0,
            float(d["co2_cost"].sum()) if "co2_cost" in d.columns else 0.0,
        )

    capex_a, opex_a, co2_a = _vals(df_a, period_a)
    capex_b, opex_b, co2_b = _vals(df_b, period_b)
    if not _co2_costs_already_in_opex_from_df(df_a):
        opex_a += co2_a
    if not _co2_costs_already_in_opex_from_df(df_b):
        opex_b += co2_b
    x = [base_name, cmp_name]
    periods = [period_a or "n/a", period_b or "n/a"]
    title_period = _period_label_for_title(period_a, period_b)

    fig.add_trace(go.Bar(
        name="CAPEX",
        x=x,
        y=[capex_a, capex_b],
        customdata=periods,
        marker=dict(color=COST_COLOR_MAP.get("CAPEX")),
        hovertemplate=f"%{{x}}<br>Periode: %{{customdata}}<br>CAPEX: %{{y:.2f}} {COST_UNIT}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="OPEX",
        x=x,
        y=[opex_a, opex_b],
        customdata=periods,
        marker=dict(color=COST_COLOR_MAP.get("OPEX")),
        hovertemplate=f"%{{x}}<br>Periode: %{{customdata}}<br>OPEX: %{{y:.2f}} {COST_UNIT}<extra></extra>",
    ))

    fig.update_layout(
        title=f"Gesamtkostenvergleich: {base_name} und {cmp_name} (CAPEX als Annuität + OPEX) - {title_period}",
        barmode="stack",
        xaxis_title="Variante",
        yaxis_title=f"Kosten [{COST_UNIT}]",
        margin=dict(l=30, r=30, t=60, b=50),
        legend_title="Kostenart",
    )
    return fig


#%% CO2 / Emissionen (Auswertung)

def _emissions_total_for_period(df_emissions: pd.DataFrame, period: str) -> float:
    """
    Summiert alle CO2-Emissionen einer bestimmten Periode.
    
    Inputs: df_emissions, period.
    Outputs: Gesamte Emissionen dieser Periode in Tonnen CO2.
    """
    if df_emissions is None or df_emissions.empty or period is None:
        return 0.0
    if "period" not in df_emissions.columns or "emissions_t" not in df_emissions.columns:
        return 0.0
    d = df_emissions[df_emissions["period"].astype(str) == str(period)].copy()
    if d.empty:
        return 0.0
    return float(pd.to_numeric(d["emissions_t"], errors="coerce").fillna(0.0).sum())


def _resolve_variant_emission_period(st: dict, df_emissions: pd.DataFrame, requested_period: str | None) -> str | None:
    """
    Sucht die passende Emissionsperiode für eine Variante.
    
    Inputs: st, df_emissions, requested_period.
    Outputs: Gültige Periode als Text.
    """
    period = _resolve_state_period(st, requested_period)
    if period is not None:
        return period
    return _resolve_df_period(df_emissions, requested_period)


def build_variant_emissions_compare_fig(
    st_base: dict,
    st_cmp: dict,
    base_name: str,
    cmp_name: str,
    period_value: str,
) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für CO2-Emissionen der Basisvariante im Vergleich zur Vergleichsvariante.
    
    Inputs: st_base, st_cmp, base_name, cmp_name, period_value.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    df_a = st_base.get("df_emissions", pd.DataFrame()) if st_base else pd.DataFrame()
    df_b = st_cmp.get("df_emissions", pd.DataFrame()) if st_cmp else pd.DataFrame()
    if df_a is None:
        df_a = pd.DataFrame()
    if df_b is None:
        df_b = pd.DataFrame()

    period_a = _resolve_variant_emission_period(st_base, df_a, period_value)
    period_b = _resolve_variant_emission_period(st_cmp, df_b, period_value)
    if period_a is None and period_b is None:
        fig.update_layout(title=f"CO2-Emissionen: {base_name} und {cmp_name} (in einer oder beiden Varianten keine CO2-Daten)")
        return fig
    emis_a = _emissions_total_for_period(df_a, period_a) if period_a is not None else 0.0
    emis_b = _emissions_total_for_period(df_b, period_b) if period_b is not None else 0.0
    fig.add_trace(go.Bar(
        x=[base_name, cmp_name],
        y=[emis_a, emis_b],
        customdata=[period_a or "n/a", period_b or "n/a"],
        marker=dict(color=px.colors.qualitative.Vivid[4] if len(px.colors.qualitative.Vivid) > 4 else "#17becf"),
        hovertemplate="%{x}<br>Periode: %{customdata}<br>%{y:.2f} t CO2/a<extra></extra>",
        name="Emissionen",
    ))
    fig.update_layout(
        title=f"CO2-Emissionen: {base_name} und {cmp_name} - {_period_label_for_title(period_a, period_b)} (Jahreswert)",
        xaxis_title="Variante",
        yaxis_title="Emissionen [t CO2/a]",
        margin=dict(l=30, r=30, t=60, b=50),
        showlegend=False,
    )
    return fig


def build_variant_abatement_cost_fig(
    st_base: dict,
    st_cmp: dict,
    base_name: str,
    cmp_name: str,
    period_value: str,
) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für CO2-Vermeidungkosten der Basisvariante zur Vergleichsvariante.
    
    Inputs: st_base, st_cmp, base_name, cmp_name, period_value.
    Outputs: Plotly-Abbildung.
    """
    fig = go.Figure()
    df_em_base = st_base.get("df_emissions", pd.DataFrame()) if st_base else pd.DataFrame()
    df_em_cmp = st_cmp.get("df_emissions", pd.DataFrame()) if st_cmp else pd.DataFrame()
    if df_em_base is None:
        df_em_base = pd.DataFrame()
    if df_em_cmp is None:
        df_em_cmp = pd.DataFrame()

    period_base = _resolve_df_period(st_base.get("df_total_cost", pd.DataFrame()), period_value)
    period_cmp = _resolve_df_period(st_cmp.get("df_total_cost", pd.DataFrame()), period_value)
    emis_period_base = period_base or _resolve_variant_emission_period(st_base, df_em_base, period_value)
    emis_period_cmp = period_cmp or _resolve_variant_emission_period(st_cmp, df_em_cmp, period_value)
    if emis_period_base is None and emis_period_cmp is None:
        return empty_info_figure(
            "CO2-Vermeidungskosten",
            "Für eine oder beide Varianten liegen keine CO2-Daten vor.",
        )
    cost_base = _total_system_cost_with_co2_for_period(st_base.get("df_total_cost", pd.DataFrame()), period_base) if period_base is not None else 0.0
    cost_cmp = _total_system_cost_with_co2_for_period(st_cmp.get("df_total_cost", pd.DataFrame()), period_cmp) if period_cmp is not None else 0.0
    emis_base = _emissions_total_for_period(df_em_base, emis_period_base) if emis_period_base is not None else 0.0
    emis_cmp = _emissions_total_for_period(df_em_cmp, emis_period_cmp) if emis_period_cmp is not None else 0.0

    delta_cost = cost_cmp - cost_base
    delta_emissions = emis_base - emis_cmp

    if abs(delta_emissions) <= 1e-9:
        return empty_info_figure(
            "CO2-Vermeidungskosten",
            "Zwischen Datenbasis und Vergleichsvariante liegt keine Emissionsdifferenz vor. Es entstehen daher keine CO2-Vermeidungskosten.",
        )
    if delta_emissions < 0:
        return empty_info_figure(
            "CO2-Vermeidungskosten",
            "Die Vergleichsvariante emittiert mehr CO2 als die Datenbasis. Es entstehen daher keine CO2-Vermeidungskosten.",
        )

    value = delta_cost / delta_emissions
    if value < 0:
        return empty_info_figure(
            "CO2-Vermeidungskosten",
            "Die Kosten der Datenbasis sind höher als die Kosten der Vergleichsvariante. Dadurch entstehen rechnerisch negative Vermeidungskosten; das Diagramm wird deshalb nicht dargestellt.",
        )
    fig.add_trace(go.Bar(
        x=["Vermeidungskosten"],
        y=[value],
        customdata=np.array([[
            delta_cost,
            delta_emissions,
            base_name,
            cmp_name,
            period_base or "n/a",
            period_cmp or "n/a",
        ]], dtype=object),
        marker=dict(color=px.colors.qualitative.Vivid[5] if len(px.colors.qualitative.Vivid) > 5 else "#8c564b"),
        hovertemplate=(
            "Datenbasis: %{customdata[2]}<br>"
            "Vergleich: %{customdata[3]}<br>"
            "Periode Datenbasis: %{customdata[4]}<br>"
            "Periode Vergleich: %{customdata[5]}<br>"
            "Delta Kosten: %{customdata[0]:.2f} EUR/Jahr<br>"
            "Vermiedene Emissionen: %{customdata[1]:.2f} t CO2/a<br>"
            "Vermeidungskosten: %{y:.2f} EUR/t CO2<extra></extra>"
        ),
        name="Vermeidungskosten",
    ))
    fig.update_layout(
        title=f"CO2-Vermeidungskosten: {cmp_name} gegenüber {base_name} - {_period_label_for_title(period_base, period_cmp)}",
        xaxis_title="Kennzahl",
        yaxis_title="Vermeidungskosten [EUR/t CO2]",
        margin=dict(l=30, r=30, t=60, b=50),
        showlegend=False,
    )
    return fig


#%% Variantenvergleich / Sensitivität - Helper (Kosten + Kapazitäten)

def _basename(nc_path: str) -> str:
    """
    Erzeugt einen robusten, kurzen Varianten-Namen aus einem Dateipfad (os.path.basename)
    
    Inputs: nc_path: str    
    
    Versucht basename, fallback '(keine Auswahl)'
    
    Outputs: str
    """
    try:
        return os.path.basename(str(nc_path)) if nc_path else "(keine Auswahl)"
    except Exception:
        return "(keine Auswahl)"



def _multicat_series_for_period(
    st: dict,
    period_value: str | None,
    by_key: str,
    value_col: str,
    component_allow: set[str] | None = None,
) -> pd.Series:
    """
    Erzeugt eine Series (index=label) für eine bestimmte Periode aus den vorbereiteten
    multicategory-Tabellen im State

    Inputs: st: dict (Dataset-State)
            period_value: str|None
            by_key: Key im State ('by_sector_p' oder 'by_sector_e')
            value_col: 'p_nom' oder 'e_nom'
            component_allow: optional set[str] um Komponenten einzuschränken
    
    Extrahiert alle Sektor-DFs unter st[by_key] und verkettet sie
    Filtert nach Periode (MIP) oder lässt alles wie gehabt (Single-year)
    Optional: filtert auf erlaubte Komponenten
    Gruppiert nach label und summiert value_col
    
    Outputs: pd.Series
    """
    if st is None or (not st.get("ok", False)):
        return pd.Series(dtype=float)

    by_sector = st.get(by_key, {})
    if not isinstance(by_sector, dict) or not by_sector:
        return pd.Series(dtype=float)

    frames = []
    for _sec, df in by_sector.items():
        if isinstance(df, pd.DataFrame) and (not df.empty):
            frames.append(df.copy())

    if not frames:
        return pd.Series(dtype=float)

    d = pd.concat(frames, ignore_index=True)

    if "label" not in d.columns or value_col not in d.columns:
        return pd.Series(dtype=float)

    # Periodenfilter
    years = st.get("years", [])
    if years:
        try:
            p = int(period_value)
        except Exception:
            return pd.Series(dtype=float)
        d = d[pd.to_numeric(d["year"], errors="coerce").fillna(-1).astype(int) == p]
    else:
        # Single-year: keine Filterung
        pass

    if d.empty:
        return pd.Series(dtype=float)

    # Komponentenfilter (z.B. nur Speicher)
    if component_allow is not None:
        if "component" not in d.columns:
            return pd.Series(dtype=float)
        allow = {str(x) for x in component_allow}
        d = d[d["component"].astype(str).isin(allow)]
        if d.empty:
            return pd.Series(dtype=float)

    s = d.groupby("label")[value_col].sum().astype(float)
    s = s.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return s


def _capacity_series_for_period(st: dict, period_value: str | None) -> pd.Series:
    """
    Liefert aktive Nennleistungen je Label für eine Periode.
    
    Inputs: st: dict
            period_value: str|None
            
    Verkettung aller Sektor-DFs aus by_sector_p
    Filter nach year == period (MIP) oder keine Filterung (Single)
    Gruppierung nach label und Summation von p_nom
    
    Outputs: pd.Series (Nennleistung in kW)
    """
    if st is None or (not st.get("ok", False)):
        return pd.Series(dtype=float)

    by_sector_p = st.get("by_sector_p", {})
    if not isinstance(by_sector_p, dict) or not by_sector_p:
        return pd.Series(dtype=float)

    frames = []
    for _sec, df in by_sector_p.items():
        if isinstance(df, pd.DataFrame) and (not df.empty):
            frames.append(df.copy())

    if not frames:
        return pd.Series(dtype=float)

    d = pd.concat(frames, ignore_index=True)
    if d.empty or "p_nom" not in d.columns or "label" not in d.columns:
        return pd.Series(dtype=float)

    years = st.get("years", [])
    if years:
        # MIP: year ist numerisch, period_value kommt als String
        try:
            p = int(period_value)
        except Exception:
            return pd.Series(dtype=float)
        d = d[pd.to_numeric(d["year"], errors="coerce").fillna(-1).astype(int) == p]
    else:
        # Single-year: year ist "" (leerer String) in prepare_multicategory
        # Keine Filterung nötig
        pass

    if d.empty:
        return pd.Series(dtype=float)

    s = d.groupby("label")["p_nom"].sum().astype(float)
    s = s.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return s


def build_variant_capacity_compare_fig(
    st_base: dict,
    st_cmp: dict,
    base_name: str,
    cmp_name: str,
    period_value: str | None,
    top_n: int = 30,
) -> go.Figure:
    """
    Vergleich der aktiven Nennleistungen je Komponente/Label (kW) 
    für ein gewähltes Jahr. Darstellung: gruppierte Balken (Variante A vs. Variante B) 
    für Top-N Labels.
    
    Inputs: st_base: dict
            st_cmp: dict
            base_name: str
            cmp_name: str
            period_value: str|None
            top_n: int
            
    Erzeugt Kapazitäts-Serien für beide Varianten via _capacity_series_for_period
    Vereint Indices, baut Vergleichs-DF und sortiert nach Maxwert
    Begrenzt auf Top-N und mappt Labels auf Anzeige-Namen
    Erstellt gruppierte Balken (A vs B) mit Hover
    
    Outputs: go.figure (Variantenvergleich Leistungen)
    """
    fig = go.Figure()

    period_a = _resolve_state_period(st_base, period_value)
    period_b = _resolve_state_period(st_cmp, period_value)
    s_a = _capacity_series_for_period(st_base, period_a)
    s_b = _capacity_series_for_period(st_cmp, period_b)

    if s_a.empty and s_b.empty:
        fig.update_layout(title="Nennleistungen (keine Daten)")
        return fig

    idx = sorted(set(s_a.index.tolist()) | set(s_b.index.tolist()))
    df = pd.DataFrame({
        base_name: s_a.reindex(idx).fillna(0.0).astype(float),
        cmp_name:  s_b.reindex(idx).fillna(0.0).astype(float),
    }, index=idx)

    df["max"] = df.max(axis=1)
    df = df[df["max"].abs() > CHART_EPS].copy()
    if df.empty:
        return empty_info_figure(
            "Nennleistungen",
            "Für die aktuelle Auswahl liegen keine Komponenten mit einer Leistung größer 0 vor.",
        )
    df = df.sort_values("max", ascending=False)

    if top_n is not None and len(df) > top_n:
        df = df.head(top_n)

    labels = df.index.tolist()
    name_map = display_name_map(labels)
    x = [name_map.get(l, l) for l in labels]
    # Variantenfarben (bewusst NICHT die Kostenfarben)
    vivid = px.colors.qualitative.Vivid
    col_a = vivid[2] if len(vivid) > 2 else None
    col_b = vivid[3] if len(vivid) > 3 else None

    fig.add_trace(go.Bar(
        name=base_name,
        x=x,
        y=df[base_name].values,
        marker=dict(color=col_a) if col_a else None,
        hovertemplate="%{x}<br>" + base_name + f" ({period_a}): " + "%{y:.2f} kW<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name=cmp_name,
        x=x,
        y=df[cmp_name].values,
        marker=dict(color=col_b) if col_b else None,
        hovertemplate="%{x}<br>" + cmp_name + f" ({period_b}): " + "%{y:.2f} kW<extra></extra>",
    ))

    period_txt = _period_label_for_title(period_a, period_b)
    fig.update_layout(
        title=f"Nennleistungen: {base_name} und {cmp_name} - {period_txt}",
        barmode="group",
        xaxis_title="Komponente",
        yaxis_title="Leistung [kW]",
        margin=dict(l=30, r=30, t=60, b=140),
        legend_title="Variante",
    )
    fig.update_xaxes(tickangle=45)
    return fig

def build_variant_storage_capacity_compare_fig(
    st_base: dict,
    st_cmp: dict,
    base_name: str,
    cmp_name: str,
    period_value: str | None,
    top_n: int = 30,
) -> go.Figure:
    """
    Vergleich der aktiven Speicherkapazitäten (kWh) für Stores + Storage Units.
    Darstellung analog zum Leistungsvergleich: gruppierte Balken, Top-N Labels.
    
    Inputs: st_base: dict
            st_cmp: dict
            base_name: str
            cmp_name: str
            period_value: str|None
            top_n: int
    
    Zieht Series via _multicat_series_for_period für by_sector_e und filtert auf
    {'stores','storage_units'}
    Vereint, sortiert nach Max, Top-N und display_name_map
    Erstellt gruppierte Balken mit Hover
    
    Outputs: go.figure (Variantenvergleich Speicherkapazität, Säulendiagramm)
    """
    fig = go.Figure()
    period_a = _resolve_state_period(st_base, period_value)
    period_b = _resolve_state_period(st_cmp, period_value)

    s_a = _multicat_series_for_period(
        st=st_base,
        period_value=period_a,
        by_key="by_sector_e",
        value_col="e_nom",
        component_allow={"stores", "storage_units"},
    )
    s_b = _multicat_series_for_period(
        st=st_cmp,
        period_value=period_b,
        by_key="by_sector_e",
        value_col="e_nom",
        component_allow={"stores", "storage_units"},
    )

    if s_a.empty and s_b.empty:
        fig.update_layout(title="Speicherkapazität (keine Daten)")
        return fig

    idx = sorted(set(s_a.index.tolist()) | set(s_b.index.tolist()))
    df = pd.DataFrame({
        base_name: s_a.reindex(idx).fillna(0.0).astype(float),
        cmp_name:  s_b.reindex(idx).fillna(0.0).astype(float),
    }, index=idx)

    df["max"] = df.max(axis=1)
    df = df[df["max"].abs() > CHART_EPS].copy()
    if df.empty:
        return empty_info_figure(
            "Speicherkapazität",
            "Für die aktuelle Auswahl liegen keine Speicherkomponenten mit einer Kapazität größer 0 vor.",
        )
    df = df.sort_values("max", ascending=False)

    if top_n is not None and len(df) > top_n:
        df = df.head(top_n)

    labels = df.index.tolist()
    name_map = display_name_map(labels)
    x = [name_map.get(l, l) for l in labels]
    # gleiche Variantenfarben wie beim Leistungs-Vergleich
    vivid = px.colors.qualitative.Vivid
    col_a = vivid[2] if len(vivid) > 2 else None
    col_b = vivid[3] if len(vivid) > 3 else None

    fig.add_trace(go.Bar(
        name=base_name,
        x=x,
        y=df[base_name].values,
        marker=dict(color=col_a) if col_a else None,
        hovertemplate="%{x}<br>" + base_name + f" ({period_a}): " + "%{y:.2f} kWh<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name=cmp_name,
        x=x,
        y=df[cmp_name].values,
        marker=dict(color=col_b) if col_b else None,
        hovertemplate="%{x}<br>" + cmp_name + f" ({period_b}): " + "%{y:.2f} kWh<extra></extra>",
    ))

    period_txt = _period_label_for_title(period_a, period_b)
    fig.update_layout(
        title=f"Speicherkapazität: {base_name} und {cmp_name} - {period_txt}",
        barmode="group",
        xaxis_title="Komponente",
        yaxis_title="Energie [kWh]",
        margin=dict(l=30, r=30, t=60, b=140),
        legend_title="Variante",
    )
    fig.update_xaxes(tickangle=45)
    return fig


def build_variant_electric_load_compare_fig(
    st_base: dict,
    st_cmp: dict,
    base_name: str,
    cmp_name: str,
) -> go.Figure:
    """
    Vergleicht die Peaks von Gesamtstromlast und Reststromlast nach Erzeugung über alle Perioden und erstellt eine Plotly-Abbildung.

    Inputs: State der Datenbasis, State der Vergleichsvariante und deren Anzeigenamen.
    Outputs: Plotly-Abbildung.
    """
    keep_series = ["Gesamtstromlast", "Reststromlast nach Erzeugung"]

    def _prep(st: dict, variant_name: str) -> pd.DataFrame:
        df = st.get("df_ops_load_metrics", pd.DataFrame())
        if df is None or df.empty:
            return pd.DataFrame(columns=["variant", "period", "series", "peak_kw"])
        d = df.copy()
        if not {"period", "series", "peak_kw"}.issubset(d.columns):
            return pd.DataFrame(columns=["variant", "period", "series", "peak_kw"])
        d = d[d["series"].astype(str).isin(keep_series)].copy()
        if d.empty:
            return pd.DataFrame(columns=["variant", "period", "series", "peak_kw"])
        d["variant"] = variant_name
        d["period"] = d["period"].astype(str)
        d["series"] = d["series"].astype(str)
        d["peak_kw"] = pd.to_numeric(d["peak_kw"], errors="coerce").fillna(0.0).astype(float)
        return d[["variant", "period", "series", "peak_kw"]]

    df = pd.concat([
        _prep(st_base, base_name),
        _prep(st_cmp, cmp_name),
    ], ignore_index=True)

    fig = go.Figure()
    if df.empty:
        fig.update_layout(title="Gesamtstromlast und Reststromlast nach Erzeugung (keine Daten)")
        return fig

    def _period_sort_key(value: str):
        try:
            return (0, int(value))
        except Exception:
            return (1, str(value))

    periods = sorted(df["period"].astype(str).unique().tolist(), key=_period_sort_key)
    df["period"] = pd.Categorical(df["period"], categories=periods, ordered=True)
    df["series"] = pd.Categorical(df["series"], categories=keep_series, ordered=True)
    df = df.sort_values(["period", "series", "variant"])

    vivid = px.colors.qualitative.Vivid
    colors = {
        base_name: vivid[2] if len(vivid) > 2 else "#4c78a8",
        cmp_name: vivid[3] if len(vivid) > 3 else "#f58518",
    }
    for variant_name in [base_name, cmp_name]:
        dv = df[df["variant"].astype(str) == str(variant_name)].copy()
        if dv.empty:
            continue
        fig.add_trace(go.Bar(
            name=variant_name,
            x=[dv["period"].astype(str).tolist(), dv["series"].astype(str).tolist()],
            y=dv["peak_kw"].astype(float).tolist(),
            marker=dict(color=colors.get(variant_name)),
            hovertemplate="%{x}<br>" + variant_name + ": %{y:.2f} kW<extra></extra>",
        ))

    fig.update_layout(
        title=f"Gesamtstromlast und Reststromlast nach Erzeugung: {base_name} und {cmp_name} je Investitionsperiode",
        barmode="group",
        xaxis_title="Investitionsperiode",
        yaxis_title="Lastspitze [kW]",
        margin=dict(l=30, r=30, t=60, b=120),
        legend_title="Variante",
    )
    return fig


#%% Sankey

def _get_energy_weights(n: pypsa.Network) -> pd.Series:
    """
    Liest Snapshot-Gewichtungen zur Energieintegration (generators oder objective) robust aus
    n.snapshot_weightings
    
    Inputs: n: pypsa.Network
    
    Wenn sw DataFrame: bevorzugt 'generators', sonst 'objective', sonst 1.0
    Wenn sw Objekt: bevorzugt Attribute generators oder objective
    Fallback: 1.0
    
    Outputs: pd.Series: Gewichtungen je Snapshot
    """
    sw = getattr(n, "snapshot_weightings", None)
    if sw is None:
        return pd.Series(1.0, index=n.snapshots, name="w")

    if isinstance(sw, pd.DataFrame):
        for col in ("generators", "objective"):
            if col in sw.columns:
                return pd.to_numeric(sw[col], errors="coerce").fillna(0.0)
        return pd.Series(1.0, index=n.snapshots, name="w")

    if hasattr(sw, "generators"):
        return pd.to_numeric(sw.generators, errors="coerce").fillna(0.0)
    if hasattr(sw, "objective"):
        return pd.to_numeric(sw.objective, errors="coerce").fillna(0.0)

    return pd.Series(1.0, index=n.snapshots, name="w")


def _filter_snapshots_by_period(n: pypsa.Network, period_value) -> pd.Index:
    """
    Filtert n.snapshots nach einer Investitionsperiode, kompatibel mit MultiIndex, 
    Tuple-Index oder DatetimeIndex
    
    Inputs: n: pypsa.Network
            period_value: beliebig (z.B. '2030', 'Single')
            
    Wenn period_value None/'Single'/'': gibt alle Snapshots zurück
    Wenn MultiIndex: filtert Level 0 auf period_value
    Wenn Tuple-Index: filtert Tuple[0] auf period_value
    Fallback: interpretiert Snapshots als Datetime und filtert nach Jahr
    
    Outputs: pd.Index: gefilterte Snapshots
    """
    snaps = pd.Index(n.snapshots)

    # "Single" / None -> alles
    if period_value is None or str(period_value) in ("Single", "", "Nur ein Zeitraum vorhanden"):
        return snaps

    # Standard-MIP: MultiIndex (period, snapshot)
    if isinstance(snaps, pd.MultiIndex):
        try:
            p = str(int(period_value))
        except Exception:
            p = str(period_value)
        lvl0 = snaps.get_level_values(0).astype(str)
        sel = snaps[lvl0 == p]
        return sel if len(sel) > 0 else snaps

    # Tuple-Index (period, snapshot) -> ohne to_datetime filtern
    if len(snaps) > 0 and isinstance(snaps[0], tuple) and len(snaps[0]) >= 2:
        try:
            p = str(int(period_value))
        except Exception:
            p = str(period_value)
        sel_list = [t for t in snaps if str(t[0]) == p]
        sel = pd.Index(sel_list)
        return sel if len(sel) > 0 else snaps

    # Fallback: Snapshots sind DatetimeIndex -> nach Jahr filtern
    dt = pd.to_datetime(snaps, errors="coerce")
    try:
        y = int(period_value)
    except Exception:
        return snaps
    mask = dt.year == y
    sel = snaps[mask]
    return sel if len(sel) > 0 else snaps


#%% Betriebsanalyse / Energiekennzahlen

# Legt den Standardnamen für die Periode fest, wenn es keine MIP gibt
OPS_DEFAULT_PERIOD = "Single"


def _ops_period_values(n: pypsa.Network) -> list[str]:
    """
    Schaut, ob das Netzwerk Investitionsjahre hat.
    
    Inputs: PyPSA-Netzwerk.
    Outputs: Liste mit Periodenwerten als Text.
    """
    years = get_investment_years(n)
    return [str(y) for y in years] if years else [OPS_DEFAULT_PERIOD]


def _ops_zero_series(n: pypsa.Network, period_value) -> pd.Series:
    """
    Erstellt eine Null-Zeitreihe für eine bestimmte Periode, damit andere Berechnungen auch dann sauber funktionieren, 
    wenn keine echten Werte vorhanden sind.
    
    Inputs: n, period_value.
    Outputs: pd.Series mit 0.0-Werten.
    """
    snaps = _filter_snapshots_by_period(n, period_value)
    return pd.Series(0.0, index=snaps, dtype=float)


def _ops_weights(n: pypsa.Network, index: pd.Index) -> pd.Series:
    """
    Bündelt die Zeitgewichtungen für bestimmte Snapshots.
    
    Inputs: n, index.
    Outputs: pd.Series mit Gewichtungen je Zeitpunkt.
    """
    w = _get_energy_weights(n).reindex(index)
    if w.isna().all():
        return pd.Series(1.0, index=index, dtype=float)
    return pd.to_numeric(w, errors="coerce").fillna(0.0).astype(float)


def _ops_column_matches(name, include_patterns=None, exclude_patterns=None) -> bool:
    """
    Prüft, ob ein Name zu bestimmten Suchmustern passt.
    Bsp. _ops_column_matches("PV_Stromnutzung_G1", ["PV"], ["Export"]) -> True, da PV enthalten ist und Export nicht.
    Bsp. _ops_column_matches("PV_Exportleitung_G1", ["PV"], ["Export"]) -> False, da da PV und Export enthalten ist.
    Damit die Betriebsanalyse nur die passenden Komponenten/Zeitreihen auswertet.
    
    Inputs: name, include_patterns, exclude_patterns.
    Outputs: True oder False.
    """
    text = str(name)
    include_patterns = include_patterns or []
    exclude_patterns = exclude_patterns or []
    if include_patterns and not any(re.search(p, text, flags=re.IGNORECASE) for p in include_patterns):
        return False
    if exclude_patterns and any(re.search(p, text, flags=re.IGNORECASE) for p in exclude_patterns):
        return False
    return True


def _ops_matching_columns(df: pd.DataFrame | None, include_patterns=None, exclude_patterns=None) -> list[str]:
    """
    Durchsucht alle Spalten eines DataFrames und gibt nur die Spalten zurück, die zu den Filterregeln passen.
    
    Inputs: df, include_patterns, exclude_patterns.
    Outputs: Liste mit passenden Spaltennamen.
    """
    if df is None or df.empty:
        return []
    return [c for c in df.columns if _ops_column_matches(c, include_patterns, exclude_patterns)]


def _ops_power_series(
    n: pypsa.Network,
    comp_name: str,
    attr: str,
    include_patterns,
    period_value,
    *,
    exclude_patterns=None,
    mode: str = "positive",
) -> pd.Series:
    """
    Sammelt aus dem Netzwerk passende Zeitreihen-Spalten, filtert sie nach Namen und summiert sie zu einer einzigen Leistungszeitreihe.
    
    Inputs: n, comp_name, attr, include_patterns, period_value, exclude_patterns, mode.
    Outputs: pd.Series mit einer aufsummierten Leistungszeitreihe.
    """
    snaps = _filter_snapshots_by_period(n, period_value)
    df = _get_dynamic_attr_df(n, comp_name, attr)
    cols = _ops_matching_columns(df, include_patterns, exclude_patterns)
    if df is None or not cols:
        return pd.Series(0.0, index=snaps, dtype=float)

    d = df.reindex(snaps)
    d = d.loc[:, [c for c in cols if c in d.columns]]
    if d.empty:
        return pd.Series(0.0, index=snaps, dtype=float)
    d = d.apply(pd.to_numeric, errors="coerce").fillna(0.0)

    if mode == "positive":
        d = d.clip(lower=0.0)
    elif mode == "negative_out":
        d = -d.clip(upper=0.0)
    elif mode == "negative_abs":
        d = d.clip(upper=0.0).abs()
    elif mode == "abs":
        d = d.abs()

    return d.sum(axis=1).astype(float)


def _ops_load_series(n: pypsa.Network, include_patterns, period_value) -> pd.Series:
    """
    Sammelt die passende Last-Zeitreihe aus dem Netzwerk.
    
    Inputs: n, include_patterns, period_value.
    Outputs: pd.Series mit der aufsummierten Last-Zeitreihe.
    """
    for attr in ("p", "p_set"):
        s = _ops_power_series(n, "loads", attr, include_patterns, period_value, mode="positive")
        if s.abs().sum() > 0:
            return s
    return _ops_zero_series(n, period_value)


def _ops_energy_kwh(n: pypsa.Network, series: pd.Series) -> float:
    """
    Rechnet eine Leistungszeitreihe in eine Energiemenge um.
    
    Inputs: n, series.
    Outputs: Energie in kWh.
    """
    if series is None or len(series) == 0:
        return 0.0
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    w = _ops_weights(n, s.index)
    return float(s.mul(w).sum())


def _ops_safe_pct(num: float, den: float, *, clamp: bool = True) -> float:
    """
    Funkrion zur Berechnung von Prozentwerten.
    
    Inputs: num, den, clamp.
    Outputs: Prozentzahl als float.
    """
    try:
        num_f = float(num)
        den_f = float(den)
    except Exception:
        return 0.0
    if not np.isfinite(num_f) or not np.isfinite(den_f) or abs(den_f) <= 1e-12:
        return 0.0
    value = 100.0 * num_f / den_f
    if clamp:
        value = max(0.0, min(100.0, value))
    return float(value)


def _ops_grid_import_series(n: pypsa.Network, period_value) -> pd.Series:
    """
    Sammelt aus den Generator-Zeitreihen den Strombezug aus dem öffentlichen Netz.
    
    Inputs: n, period_value.
    Outputs: pd.Series mit der Stromnetzbezugs-Leistung über die Zeit.
    """
    return _ops_power_series(n, "generators", "p", [r"Stromnetz_Bezug"], period_value, mode="positive")


def _ops_electric_export_series(n: pypsa.Network, period_value) -> pd.Series:
    """
    Berechnet, wie viel Strom in einer Periode exportiert/eingespeist wird.
    
    Inputs: n, period_value.
    Outputs: pd.Series mit der gesamten Stromexport-Leistung über die Zeit.
    """
    pv = _ops_power_series(n, "links", "p0", [r"PV_Exportleitung"], period_value, mode="positive")
    chp = _ops_power_series(n, "links", "p0", [r"BHKW_Exportleitung"], period_value, mode="positive")
    return pv.add(chp, fill_value=0.0)


def _ops_local_electric_generation_series(n: pypsa.Network, period_value) -> pd.Series:
    """
    Berechnet, wie viel lokal erzeugter Strom aus PV und BHKW im Quartier selbst genutzt wird.
    
    Inputs: n, period_value.
    Outputs: pd.Series mit lokal erzeugtem und intern genutztem Strom über die Zeit.
    """
    pv_self = _ops_power_series(n, "links", "p1", [r"PV_Stromnutzung"], period_value, mode="negative_out")
    chp_self = _ops_power_series(n, "links", "p1", [r"BHKW_Stromnutzung"], period_value, mode="negative_out")
    return pv_self.add(chp_self, fill_value=0.0)


def _ops_heat_pump_electricity_series(n: pypsa.Network, period_value) -> pd.Series:
    """
    Ermittelt aus den Link-Zeitreihen die Eingangsleistung p0 der Wärmepumpe.
    
    Inputs: n, period_value.
    Outputs: pd.Series mit dem Stromverbrauch der Wärmepumpe über die Zeit.
    """
    return _ops_power_series(n, "links", "p0", [r"W.*rmepumpe"], period_value, mode="positive")


def _ops_electric_storage_charge_series(n: pypsa.Network, period_value) -> pd.Series:
    """
    Ermittelt für die Zeitreihe, wie stark der Stromspeicher geladen wird.
    
    Inputs: n, period_value.
    Outputs: pd.Series mit der Ladeleistung des Stromspeichers über die Zeit.
    """
    return _ops_power_series(n, "links", "p0", [r"Stromspeicher_Laden"], period_value, mode="positive")


def _ops_electric_storage_discharge_series(n: pypsa.Network, period_value) -> pd.Series:
    """
    Ermittelt für die Zeitreihe, wie stark der Stromspeicher entladen wird.
    
    Inputs: n, period_value.
    Outputs: pd.Series mit der Entladeleistung des Stromspeichers über die Zeit.
    """
    return _ops_power_series(n, "links", "p1", [r"Stromspeicher_Entladen"], period_value, mode="negative_out")


def _ops_total_electric_demand_series(n: pypsa.Network, period_value) -> pd.Series:
    """
    Berechnet den gesamten Strombedarf des Systems für eine Periode.
    
    Inputs: n, period_value.
    Outputs: pd.Series mit dem gesamten elektrischen Bedarf über die Zeit.
    """
    load = _ops_load_series(n, [r"Stromlast"], period_value)
    heat_pump_input = _ops_heat_pump_electricity_series(n, period_value).reindex(load.index).fillna(0.0)
    storage_charge = _ops_electric_storage_charge_series(n, period_value).reindex(load.index).fillna(0.0)
    return load.add(heat_pump_input, fill_value=0.0).add(storage_charge, fill_value=0.0)


def _ops_pv_generation_series(n: pypsa.Network, period_value) -> pd.Series:
    """
    Bestimmt die gesamte PV-Erzeugung für eine Periode.
    
    Inputs: n, period_value.
    Outputs: pd.Series mit der PV-Erzeugung über die Zeit.
    """
    pv_generation = _ops_power_series(
        n,
        "generators",
        "p",
        [r"^PV(?:_[A-Za-z0-9]+)*_\d{4}$", r"^PV$"],
        period_value,
        exclude_patterns=[r"Einspeisung", r"Export", r"Stromnutzung"],
        mode="positive",
    )
    if pv_generation.abs().sum() > 1e-9:
        return pv_generation

    pv_self = _ops_power_series(n, "links", "p1", [r"PV_Stromnutzung"], period_value, mode="negative_out")
    pv_export = _ops_power_series(n, "links", "p0", [r"PV_Exportleitung"], period_value, mode="positive")
    return pv_self.add(pv_export, fill_value=0.0)


def _ops_period_energy_bundle(n: pypsa.Network, period_value: str) -> dict[str, float]:
    """
    Sammelt für eine Periode alle wichtigen Betriebsenergien des Systems.
    Wie: PV-Erzeugung, PV-Eigenverbrauch, PV-Einspeisung, Wärmepumpenstrom, Wärmepumpenwärme, Stromlast etc.
    
    Inputs: n, period_value.
    Outputs: Dictionary mit verschiedenen Energie-Kennzahlen in kWh.
    """
    el_load = _ops_load_series(n, [r"Stromlast"], period_value)
    total_el_demand = _ops_total_electric_demand_series(n, period_value)
    heat_load = _ops_load_series(n, [r"W.*rmelast"], period_value)

    grid_el = _ops_grid_import_series(n, period_value)
    heat_grid = _ops_power_series(n, "generators", "p", [r"Fern.*rme_Bezug"], period_value, mode="positive")
    gas_import = _ops_power_series(n, "generators", "p", [r"Gasnetz_Bezug"], period_value, mode="positive")

    pv_gen = _ops_pv_generation_series(n, period_value)
    pv_self = _ops_power_series(n, "links", "p1", [r"PV_Stromnutzung"], period_value, mode="negative_out")
    pv_export = _ops_power_series(n, "links", "p0", [r"PV_Exportleitung"], period_value, mode="positive")
    chp_el = _ops_power_series(n, "links", "p1", [r"BHKW_Stromnutzung"], period_value, mode="negative_out")
    storage_charge = _ops_electric_storage_charge_series(n, period_value)
    storage_discharge = _ops_electric_storage_discharge_series(n, period_value)

    solar_heat = _ops_power_series(n, "generators", "p", [r"Solarthermie"], period_value, mode="positive")
    heat_pump_el = _ops_heat_pump_electricity_series(n, period_value)
    heat_pump = _ops_power_series(n, "links", "p1", [r"W.*rmepumpe"], period_value, mode="negative_out")
    gas_boiler = _ops_power_series(n, "links", "p1", [r"Gaskessel"], period_value, mode="negative_out")
    chp_heat = _ops_power_series(n, "links", "p2", [r"^BHKW_\d{4}$"], period_value, mode="negative_out")

    return {
        "electric_load_kwh": _ops_energy_kwh(n, el_load),
        "total_electric_demand_kwh": _ops_energy_kwh(n, total_el_demand),
        "heat_load_kwh": _ops_energy_kwh(n, heat_load),
        "grid_import_kwh": _ops_energy_kwh(n, grid_el),
        "electric_export_kwh": _ops_energy_kwh(n, _ops_electric_export_series(n, period_value)),
        "heat_grid_import_kwh": _ops_energy_kwh(n, heat_grid),
        "gas_import_kwh": _ops_energy_kwh(n, gas_import),
        "pv_generation_kwh": _ops_energy_kwh(n, pv_gen),
        "pv_self_consumption_kwh": _ops_energy_kwh(n, pv_self),
        "pv_feed_in_kwh": _ops_energy_kwh(n, pv_export),
        "chp_electricity_kwh": _ops_energy_kwh(n, chp_el),
        "electric_storage_charge_kwh": _ops_energy_kwh(n, storage_charge),
        "electric_storage_discharge_kwh": _ops_energy_kwh(n, storage_discharge),
        "solar_heat_kwh": _ops_energy_kwh(n, solar_heat),
        "heat_pump_electricity_kwh": _ops_energy_kwh(n, heat_pump_el),
        "heat_pump_heat_kwh": _ops_energy_kwh(n, heat_pump),
        "gas_boiler_heat_kwh": _ops_energy_kwh(n, gas_boiler),
        "chp_heat_kwh": _ops_energy_kwh(n, chp_heat),
    }


def build_ops_load_metrics_df(n: pypsa.Network) -> pd.DataFrame:
    """
    Erstellt den DataFrame welcher zeigt, wie hoch verschiedene Lastkurven sind.
    
    Inputs: n.
    Outputs: DataFrame mit Last-Kennzahlen je Periode und Zeitreihe.
    """
    cols = ["period", "series", "peak_kw", "min_kw", "mean_kw", "hours_above_80pct_peak"]
    if n is None:
        return pd.DataFrame(columns=cols)
    rows = []
    for period in _ops_period_values(n):
        total_load = _ops_total_electric_demand_series(n, period)
        electric_export = _ops_electric_export_series(n, period).reindex(total_load.index).fillna(0.0)
        local_generation = _ops_local_electric_generation_series(n, period).reindex(total_load.index).fillna(0.0)
        curves = {
            "Stromlast": _ops_load_series(n, [r"Stromlast"], period),
            "Gesamtstromlast": total_load,
            "Netto-Stromlast": total_load.sub(electric_export, fill_value=0.0),
            "Reststromlast nach Erzeugung": total_load.sub(local_generation, fill_value=0.0).clip(lower=0.0),
            "Wärmelast": _ops_load_series(n, [r"W.*rmelast"], period),
        }
        for label, s in curves.items():
            if s is None or len(s) == 0:
                continue
            s = pd.to_numeric(s, errors="coerce").fillna(0.0)
            peak = float(s.max()) if len(s) else 0.0
            threshold = 0.8 * peak if peak > 0 else np.inf
            hours = float(_ops_weights(n, s.index).where(s >= threshold, 0.0).sum()) if np.isfinite(threshold) else 0.0
            rows.append({
                "period": period,
                "series": label,
                "peak_kw": peak,
                "min_kw": float(s.min()) if len(s) else 0.0,
                "mean_kw": float(s.mean()) if len(s) else 0.0,
                "hours_above_80pct_peak": hours,
            })
    return pd.DataFrame(rows, columns=cols)


def build_ops_autarky_df(n: pypsa.Network) -> pd.DataFrame:
    """
    Erstellt den DataFrame für Autarkie- und PV-Kennzahlen.
    
    Inputs: n.
    Outputs: DataFrame mit Autarkie- und PV-Kennzahlen je Periode.
    """
    rows = []
    for period in _ops_period_values(n):
        b = _ops_period_energy_bundle(n, period)
        external_heat_delivery = b["heat_grid_import_kwh"] + b["gas_boiler_heat_kwh"] + b["chp_heat_kwh"]
        electric_demand = b.get("total_electric_demand_kwh", b["electric_load_kwh"])
        rows.append({
            "period": period,
            **b,
            "electric_autarky_pct": 100.0 - _ops_safe_pct(b["grid_import_kwh"], electric_demand),
            "heat_autarky_pct": 100.0 - _ops_safe_pct(external_heat_delivery, b["heat_load_kwh"]),
            "pv_self_consumption_pct": _ops_safe_pct(b["pv_self_consumption_kwh"], b["pv_generation_kwh"]),
            "pv_feed_in_pct": _ops_safe_pct(b["pv_feed_in_kwh"], b["pv_generation_kwh"]),
        })
    return pd.DataFrame(rows)


def build_ops_pv_usage_df(n: pypsa.Network) -> pd.DataFrame:
    """
    Erstellt den DataFrame für die PV-Auswertung.
    
    Inputs: n.
    Outputs: DataFrame mit PV-Nutzungswerten je Periode.
    """
    rows = []
    for period in _ops_period_values(n):
        b = _ops_period_energy_bundle(n, period)
        for metric, value in [
            ("PV-Erzeugung", b["pv_generation_kwh"]),
            ("PV-Eigenverbrauch", b["pv_self_consumption_kwh"]),
            ("PV-Einspeisung", b["pv_feed_in_kwh"]),
            ("Strombezug", b["grid_import_kwh"]),
        ]:
            rows.append({"period": period, "metric": metric, "energy_kwh": float(value)})
    return pd.DataFrame(rows)


def build_ops_technology_shares_df(n: pypsa.Network) -> pd.DataFrame:
    """
    Berechnet, welchen Anteil verschiedene Technologien an der Strom- und Wärmeversorgung haben.
    
    Inputs: n.
    Outputs: DataFrame mit Technologieanteilen je Periode.
    """
    rows = []
    for period in _ops_period_values(n):
        b = _ops_period_energy_bundle(n, period)
        electric_denom = b["electric_load_kwh"] + b["heat_pump_electricity_kwh"]
        techs = [
            ("Strom", "Netzbezug", b["grid_import_kwh"], electric_denom),
            ("Strom", "PV", b["pv_self_consumption_kwh"], electric_denom),
            ("Strom", "BHKW", b["chp_electricity_kwh"], electric_denom),
            ("Wärme", "Fernwärme", b["heat_grid_import_kwh"], b["heat_load_kwh"]),
            ("Wärme", "Solarthermie", b["solar_heat_kwh"], b["heat_load_kwh"]),
            ("Wärme", "Wärmepumpe", b["heat_pump_heat_kwh"], b["heat_load_kwh"]),
            ("Wärme", "Gaskessel", b["gas_boiler_heat_kwh"], b["heat_load_kwh"]),
            ("Wärme", "BHKW", b["chp_heat_kwh"], b["heat_load_kwh"]),
        ]
        by_sector_total = {}
        for sector, _tech, energy, _denom in techs:
            by_sector_total[sector] = by_sector_total.get(sector, 0.0) + max(float(energy), 0.0)

        for sector, tech, energy, denom in techs:
            energy = max(float(energy), 0.0)
            total = by_sector_total.get(sector, 0.0)
            if total > 0.0 and float(denom or 0.0) > 0.0:
                energy = energy * float(denom) / total
            rows.append({
                "period": period,
                "sector": sector,
                "technology": tech,
                "energy_kwh": energy,
                "share_pct": _ops_safe_pct(energy, denom, clamp=False),
            })
    return pd.DataFrame(rows)


def _ops_filter_period(df: pd.DataFrame, period_value) -> pd.DataFrame:
    """
    Filtert die Daten der Betriebsanalyse auf eine bestimmte Periode.
    
    Inputs: df, period_value.
    Outputs: Gefilterter DataFrame mit nur dieser Periode.
    """
    if df is None or df.empty or "period" not in df.columns:
        return pd.DataFrame()
    d = df[df["period"].astype(str) == str(period_value)].copy()
    if d.empty and period_value is not None:
        d = df.iloc[0:0].copy()
    return d


def build_ops_load_metrics_table_fig(df_load_metrics: pd.DataFrame, period_value) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für die verschiedenen Lastkennzahlen.
    
    Inputs: df_load_metrics, period_value.
    Outputs: Plotly-Abbildung.
    """
    d = _ops_filter_period(df_load_metrics, period_value)
    if d.empty:
        return go.Figure().update_layout(title="Lastkennzahlen (keine Daten)")
    logic_map = {
        "Stromlast": "direkte elektrische Last",
        "Gesamtstromlast": "Stromlast plus Wärmepumpe und Speicherladung",
        "Netto-Stromlast": "Gesamtstromlast minus Stromeinspeisung",
        "Reststromlast nach Erzeugung": "Gesamtstromlast minus lokale Stromerzeugung",
        "Wärmelast": "thermische Endlast",
    }
    d = d.copy()
    d["logic"] = d["series"].astype(str).map(logic_map).fillna("aus Zeitreihe berechnet")
    row_height = 44
    fig_height = max(460, 120 + row_height * (len(d) + 1))
    fig = go.Figure(data=[go.Table(
        columnwidth=[1.35, 3.35, 1.0, 1.0, 1.0, 1.25],
        header=dict(
            values=["<b>Lastgröße</b>", "<b>Rechenlogik</b>", "<b>Peak [kW]</b>", "<b>Minimum [kW]</b>", "<b>Mittel [kW]</b>", "<b>h >= 80 % Peak</b>"],
            fill_color="#f2f4f8",
            align="left",
            height=46,
            font=dict(size=15, color="#1f3555"),
        ),
        cells=dict(values=[
            d["series"],
            d["logic"],
            d["peak_kw"].map(lambda v: format_number_de(v, 2)),
            d["min_kw"].map(lambda v: format_number_de(v, 2)),
            d["mean_kw"].map(lambda v: format_number_de(v, 2)),
            d["hours_above_80pct_peak"].map(lambda v: format_number_de(v, 1)),
        ], align="left", height=row_height, font=dict(size=14, color="#1f3555")),
    )])
    fig.update_layout(title=f"Lastkennzahlen - {period_value}", height=fig_height, margin=dict(l=20, r=20, t=82, b=24))
    return fig


def build_ops_load_duration_fig(n: pypsa.Network, period_value) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für die verschiedenen Lastdauerlinie über ein Jahr.
    
    Inputs: n, period_value.
    Outputs: Plotly-Abbildung.
    """
    if n is None:
        return go.Figure().update_layout(title="Lastdauerlinie (keine Daten)")
    total_load = _ops_total_electric_demand_series(n, period_value)
    electric_export = _ops_electric_export_series(n, period_value).reindex(total_load.index).fillna(0.0)
    local_generation = _ops_local_electric_generation_series(n, period_value).reindex(total_load.index).fillna(0.0)
    curves = {
        "Stromlast": _ops_load_series(n, [r"Stromlast"], period_value),
        "Gesamtstromlast": total_load,
        "Netto-Stromlast": total_load.sub(electric_export, fill_value=0.0),
        "Reststromlast nach Erzeugung": total_load.sub(local_generation, fill_value=0.0).clip(lower=0.0),
        "Wärmelast": _ops_load_series(n, [r"W.*rmelast"], period_value),
    }
    fig = go.Figure()
    for label, s in curves.items():
        s = pd.to_numeric(s, errors="coerce").fillna(0.0)
        if s.empty:
            continue
        order = s.sort_values(ascending=False)
        weights = _ops_weights(n, order.index)
        x = weights.cumsum().to_numpy(dtype=float)
        y = order.to_numpy(dtype=float)
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=label))
    fig.update_layout(
        title=f"Lastdauerlinie - {period_value}",
        xaxis_title="Kumulierte Stunden nach absteigender Last",
        yaxis_title="Leistung [kW]",
        height=480,
        margin=dict(l=40, r=25, t=60, b=50),
    )
    return fig


def build_ops_autarky_fig(df_autarky: pd.DataFrame, period_value) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für Autarkie und Eigenverbrauch.
    
    Inputs: df_autarky, period_value.
    Outputs: Plotly-Abbildung.
    """
    d = _ops_filter_period(df_autarky, period_value)
    if d.empty:
        return go.Figure().update_layout(title="Autarkie & Eigenverbrauch (keine Daten)")
    r = d.iloc[0]
    labels = [
        "Strom-Autarkie", "Wärme-Autarkie",
        "PV-Eigenverbrauch", "PV-Einspeisequote",
    ]
    values = [
        r.get("electric_autarky_pct", 0.0), r.get("heat_autarky_pct", 0.0),
        r.get("pv_self_consumption_pct", 0.0), r.get("pv_feed_in_pct", 0.0),
    ]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=px.colors.qualitative.Vivid[:len(labels)]))
    fig.update_traces(hovertemplate="%{x}<br>%{y:.2f} %<extra></extra>")
    fig.update_layout(
        title=f"Autarkie & Eigenverbrauch - {period_value}",
        yaxis_title="Anteil [%]",
        yaxis=dict(range=[0, max(100, max(values) * 1.1 if values else 100)]),
        height=420,
        margin=dict(l=40, r=25, t=60, b=90),
        showlegend=False,
    )
    fig.update_xaxes(tickangle=25)
    return fig


def build_ops_pv_usage_fig(df_pv_usage: pd.DataFrame) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für die Kennzahlen der PV-Nutzung.
    
    Inputs: df_pv_usage.
    Outputs: Plotly-Abbildung.
    """
    if df_pv_usage is None or df_pv_usage.empty:
        return go.Figure().update_layout(title="PV-Nutzung (keine Daten)")
    fig = go.Figure()
    colors = make_label_color_map(df_pv_usage["metric"].astype(str).unique().tolist())
    for metric, d in df_pv_usage.groupby("metric", sort=False):
        fig.add_trace(go.Bar(
            x=d["period"].astype(str),
            y=d["energy_kwh"],
            name=str(metric),
            marker_color=colors.get(str(metric)),
            hovertemplate="%{x}<br>%{y:.2f} kWh<extra></extra>",
        ))
    fig.update_layout(
        title="PV-Eigenverbrauch, Einspeisung und Strombezug",
        xaxis_title="Periode",
        yaxis_title="Energie [kWh/a]",
        barmode="group",
        height=430,
        margin=dict(l=40, r=25, t=60, b=55),
        legend_title="Kennzahl",
    )
    return fig


def build_ops_technology_share_fig(df_shares: pd.DataFrame, sector: str) -> go.Figure:
    """
    Erstellt die Plotly-Abbildung für die Deckungsanteile der einzelnen Technologien und Investitionsperioden.
    
    Inputs: df_shares, sector.
    Outputs: Plotly-Abbildung.
    """
    if df_shares is None or df_shares.empty:
        return go.Figure().update_layout(title=f"Deckungsanteile {sector} nach Technologie (keine Daten)")
    d = df_shares[df_shares["sector"].astype(str).eq(str(sector))].copy()
    if d.empty:
        return go.Figure().update_layout(title=f"Deckungsanteile {sector} nach Technologie (keine Daten)")
    fig = go.Figure()
    colors = make_label_color_map(d["technology"].astype(str).unique().tolist())
    for tech, dd in d.groupby("technology", sort=False):
        fig.add_trace(go.Bar(
            x=dd["period"].astype(str),
            y=dd["share_pct"],
            name=str(tech),
            marker_color=colors.get(str(tech)),
            customdata=dd["energy_kwh"],
            hovertemplate="%{x}<br>" + str(tech) + "<br>%{y:.2f} %<br>%{customdata:.2f} kWh/a<extra></extra>",
        ))
    fig.update_layout(
        title=f"Deckungsanteile {sector} nach Technologie und Investitionsperiode",
        xaxis_title="Investitionsperiode",
        yaxis_title="Anteil an der Last [%]",
        barmode="stack",
        height=460,
        margin=dict(l=40, r=25, t=60, b=55),
        legend_title="Technologie",
    )
    return fig


def build_sankey_fig(
    n: pypsa.Network,
    df_life: pd.DataFrame | None = None,
    period_value=None,
    max_links: int | None = None,
    value_unit: str = "MWh",
    meta_ts: pd.DataFrame | None = None,            
    ts_color_map: dict[str, str] | None = None,
) -> go.Figure:
    """
    Erstellt ein Sankey-Diagramm der integrierten Energieflüsse (MWh) aus Generators, Loads,
    Storage Units, Links und Lines. Optional werden Farben aus den Zeitreihen übernommen
    und aktive Assets je Periode gefiltert.
    
    Inputs: n: pypsa.Network
            df_life: Lifetime-DF (optional)
            period_value: Investitionsperiode oder None
            max_links: optional Top-K Links (nach Flussstärke)
            value_unit: Anzeigeeinheit (intern wird kWh->MWh dividiert)
            meta_ts: Meta-DF der Zeitreihen (optional)
            ts_color_map: dict Zeitreihen-Spalte -> Farbe (optional)
            
    Bestimmt relevante Snapshots per _filter_snapshots_by_period und Gewichte per
    _get_energy_weights
    Wenn df_life+period vorhanden: filtert auf aktive Assets
    Aggregiert Flüsse: Generator->Bus (und ggf. Bus->Generator bei negativen/exportartigen),
    Bus->Load, Bus<->StorageUnit, Bus<->Link, Bus<->Line
    Konsolidiert Stores auf ihren Bus (Busknoten wird als Storelabel gezeigt), optional farblich
    aus Zeitreihen abgeleitet
    Reduziert optional auf Top-K Kanten, skaliert kWh->MWh
    Erzeugt go.Sankey mit Node-Labels, Node-Farben und Hovertemplate
    
    Outputs: go.figure (Sankey-Diagramm)
    """

    snaps_sel = _filter_snapshots_by_period(n, period_value)
    if len(snaps_sel) == 0:
        return go.Figure().update_layout(title="Sankey-Diagramm (keine Werte gefunden)")

    w = _get_energy_weights(n).reindex(snaps_sel).fillna(0.0)

    comps_with_life = set()
    active_set: set[tuple[str, str]] = set()

    if df_life is not None and not df_life.empty and period_value is not None:
        comps_with_life = set(df_life["component"].astype(str).unique())
        active_set = active_assets_in_period(df_life, period_value)

    def _is_active(component: str, name: str) -> bool:
        if not comps_with_life:
            return True
        if component not in comps_with_life:
            return True
        return (component, str(name)) in active_set

    # Farbableitung: gleiche Quelle wie Zeitreihen (meta_ts + ts_color_map)
    def _asset_color(comp: str, asset: str) -> str | None:
        if meta_ts is None or meta_ts.empty or not ts_color_map:
            return None

        m = meta_ts[
            (meta_ts["component"].astype(str) == str(comp)) &
            (meta_ts["asset"].astype(str) == str(asset))
        ]
        if m.empty:
            return None

        pref = {
            "generators": ["p"],
            "loads": ["p", "p_set"],
            "storage_units": ["p"],
            "stores": ["p"],
            "links": ["p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9"],
            "lines": ["p0", "p1"],
        }

        for a in pref.get(str(comp), []):
            cols = m[m["attr"].astype(str) == a].index.tolist()
            for c in cols:
                col = ts_color_map.get(str(c))
                if col:
                    return col

        # Fallback: erste passende TS-Spalte
        for c in m.index.tolist():
            col = ts_color_map.get(str(c))
            if col:
                return col
        return None

    key_to_label: dict[str, str] = {}
    key_to_color: dict[str, str] = {}

    def _register_node(key: str, label: str, color: str | None = None) -> str:
        if key not in key_to_label:
            key_to_label[key] = label
        if color and (key not in key_to_color):
            key_to_color[key] = color
        return key

    # Stores mit separatem Bus "zusammenziehen" (wie bisher), aber mit Farbe aus Store-TS
    store_by_bus: dict[str, list[str]] = {}
    if (
        hasattr(n, "stores") and n.stores is not None and (not n.stores.empty)
        and ("bus" in n.stores.columns)
    ):
        for st_name, b in n.stores["bus"].dropna().astype(str).items():
            if not _is_active("stores", st_name):
                continue
            b = str(b).strip()
            if b:
                store_by_bus.setdefault(b, []).append(str(st_name))

    def _bus_node(bus: str) -> str:
        b = str(bus).strip()
        if not b:
            return _register_node("bus::(unknown)", "(unknown)", "rgba(200,200,200,0.85)")

        # Falls Bus ein/mehrere Stores trägt: Label ersetzen
        if b in store_by_bus and len(store_by_bus[b]) > 0:
            sts_raw = store_by_bus[b]
            sts_disp = [strip_prefix(s) for s in sts_raw]

            if len(sts_disp) == 1:
                label = sts_disp[0]
            elif len(sts_disp) == 2:
                label = f"{sts_disp[0]} + {sts_disp[1]}"
            else:
                label = f"{sts_disp[0]} + {sts_disp[1]} (+{len(sts_disp)-2})"

            # Farbe vom ersten Store ableiten (konsistent, deterministisch)
            col = _asset_color("stores", sts_raw[0])
            return _register_node(f"busstore::{b}", label, col or "rgba(200,200,200,0.85)")

        return _register_node(f"bus::{b}", strip_prefix(b), "rgba(200,200,200,0.85)")

    def _gen_node(gen: str) -> str:
        g = str(gen).strip()
        return _register_node(f"gen::{g}", strip_prefix(g), _asset_color("generators", g))

    def _load_node(ld: str) -> str:
        l = str(ld).strip()
        return _register_node(f"load::{l}", strip_prefix(l), _asset_color("loads", l))

    def _link_node(lk: str) -> str:
        l = str(lk).strip()
        return _register_node(f"link::{l}", strip_prefix(l), _asset_color("links", l))

    def _line_node(ln: str) -> str:
        l = str(ln).strip()
        return _register_node(f"line::{l}", strip_prefix(l), _asset_color("lines", l))

    def _su_node(su: str) -> str:
        s = str(su).strip()
        return _register_node(f"su::{s}", strip_prefix(s), _asset_color("storage_units", s))

    edges: dict[tuple[str, str], float] = {}

    def add_edge(src_key: str, dst_key: str, val: float):
        try:
            v = float(val)
        except Exception:
            return
        if not np.isfinite(v) or v <= 0.0:
            return
        edges[(src_key, dst_key)] = edges.get((src_key, dst_key), 0.0) + v

    def _is_export_like_generator(gen_name: str) -> bool:
        name_l = str(gen_name).lower()
        if "einspeisung" in name_l:
            return True
        if hasattr(n, "generators") and (gen_name in n.generators.index) and ("sign" in n.generators.columns):
            s = n.generators.at[gen_name, "sign"]
            if s is not None and not pd.isna(s):
                try:
                    return float(s) < 0.0
                except Exception:
                    pass
        return False

    # --- GENERATORS ---
    if hasattr(n, "components") and hasattr(n.components, "generators"):
        dyn = n.components.generators.dynamic
        p = dyn.get("p")
        if p is not None and not p.empty:
            psel = p.reindex(snaps_sel)
        if p is not None and not p.empty:
            psel = p.reindex(snaps_sel)
            for gen in psel.columns:
                if gen not in n.generators.index:
                    continue
                if not _is_active("generators", gen):
                    continue

                bus = n.generators.at[gen, "bus"]
                if bus is None or pd.isna(bus) or str(bus).strip() == "":
                    continue

                s = psel[gen].copy()
                e_pos = s.clip(lower=0.0).mul(w).sum()
                e_neg = (-s.clip(upper=0.0)).mul(w).sum()

                if _is_export_like_generator(gen):
                    add_edge(_bus_node(bus), _gen_node(gen), e_pos)
                    add_edge(_gen_node(gen), _bus_node(bus), e_neg)
                else:
                    add_edge(_gen_node(gen), _bus_node(bus), e_pos)
                    add_edge(_bus_node(bus), _gen_node(gen), e_neg)

    # --- LOADS ---
    if hasattr(n, "components") and hasattr(n.components, "loads"):
        dyn = n.components.loads.dynamic
        p = dyn.get("p")
        if p is None or p.empty:
            p = dyn.get("p_set")
        if p is not None and not p.empty:
            psel = p.reindex(snaps_sel)
            cons = psel.clip(lower=0.0).mul(w, axis=0).sum(axis=0)
            for ld, e in cons.items():
                if ld not in n.loads.index:
                    continue
                bus = n.loads.at[ld, "bus"]
                if bus is None or pd.isna(bus) or str(bus).strip() == "":
                    continue
                add_edge(_bus_node(bus), _load_node(ld), e)

    # --- STORAGE_UNITS ---
    if hasattr(n, "components") and hasattr(n.components, "storage_units"):
        dyn = n.components.storage_units.dynamic
        p = dyn.get("p")
        if p is not None and not p.empty:
            psel = p.reindex(snaps_sel)
            charge = (-psel.clip(upper=0.0)).mul(w, axis=0).sum(axis=0)
            discharge = (psel.clip(lower=0.0)).mul(w, axis=0).sum(axis=0)
            for su in psel.columns:
                if su not in n.storage_units.index:
                    continue
                if not _is_active("storage_units", su):
                    continue

                bus = n.storage_units.at[su, "bus"]
                if bus is None or pd.isna(bus) or str(bus).strip() == "":
                    continue
                su_k = _su_node(su)
                b_k = _bus_node(bus)
                add_edge(b_k, su_k, float(charge.get(su, 0.0)))
                add_edge(su_k, b_k, float(discharge.get(su, 0.0)))

    # --- LINKS ---
    if hasattr(n, "components") and hasattr(n.components, "links"):
        dyn = n.components.links.dynamic
        ports = get_existing_link_ports(n, max_i=9)
        for i in ports:
            attr = f"p{i}"
            p = dyn.get(attr)
            if p is None or p.empty:
                continue
            psel = p.reindex(snaps_sel)

            for link in psel.columns:
                if link not in n.links.index:
                    continue
                if not _is_active("links", link):
                    continue

                bus_col = f"bus{i}"
                if bus_col not in n.links.columns:
                    continue
                bus = n.links.at[link, bus_col]
                if bus is None or pd.isna(bus) or str(bus).strip() == "":
                    continue

                series = psel[link]
                e_out = series.clip(lower=0.0).mul(w).sum()
                e_in  = (-series.clip(upper=0.0)).mul(w).sum()

                b_k = _bus_node(bus)
                l_k = _link_node(link)

                add_edge(b_k, l_k, e_out)
                add_edge(l_k, b_k, e_in)

    # --- LINES ---
    if hasattr(n, "components") and hasattr(n.components, "lines"):
        dyn = n.components.lines.dynamic

        for i in (0, 1):
            attr = f"p{i}"
            p = dyn.get(attr)
            if p is None or p.empty:
                continue

            psel = p.reindex(snaps_sel)

            for line in psel.columns:
                if line not in n.lines.index:
                    continue
                if not _is_active("lines", line):
                    continue

                bus_col = f"bus{i}"
                if bus_col not in n.lines.columns:
                    continue
                bus = n.lines.at[line, bus_col]
                if bus is None or pd.isna(bus) or str(bus).strip() == "":
                    continue

                series = psel[line]

                # Konvention: p_i > 0 => Bus(i) -> Line, p_i < 0 => Line -> Bus(i)
                e_in_to_line  = series.clip(lower=0.0).mul(w).sum()
                e_out_of_line = (-series.clip(upper=0.0)).mul(w).sum()

                b_k = _bus_node(bus)
                ln_k = _line_node(line)

                add_edge(b_k, ln_k, e_in_to_line)
                add_edge(ln_k, b_k, e_out_of_line)

    items = [(k, v) for (k, v) in edges.items() if v > 0.0]
    items.sort(key=lambda kv: kv[1], reverse=True)
    if max_links is not None and len(items) > max_links:
        items = items[:max_links]

    # --- kWh -> MWh ---
    items = [(k, float(v) / 1000.0) for (k, v) in items if np.isfinite(v)]
    items = [(k, v) for (k, v) in items if v > 0.0]

    if not items:
        title = "Sankey-Diagramm (keine Werte > 0 gefunden)"
        if isinstance(pd.Index(n.snapshots), pd.MultiIndex) and period_value is not None:
            title += f" - Investitionsperiode {period_value}"
        return go.Figure().update_layout(title=title)

    node_index: dict[str, int] = {}
    labels: list[str] = []
    node_colors: list[str] = []

    def idx(key: str) -> int:
        if key not in node_index:
            node_index[key] = len(labels)
            labels.append(key_to_label.get(key, key))
            node_colors.append(key_to_color.get(key, "rgba(200,200,200,0.85)"))
        return node_index[key]

    sources, targets, values = [], [], []

    for (src_key, dst_key), v in items:
        sources.append(idx(src_key))
        targets.append(idx(dst_key))
        values.append(float(v))

    title = ""
    if isinstance(pd.Index(n.snapshots), pd.MultiIndex) and period_value is not None:
        title += f" - Investitionsperiode {period_value}"

    fig = go.Figure(
        data=[go.Sankey(
            arrangement="snap",
            node=dict(
                label=labels,
                color=node_colors,
                pad=14,
                thickness=14,
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                hovertemplate="%{source.label} → %{target.label}<br>%{value:.2f}  MWh<extra></extra>",
            ),
        )]
    )
    fig.update_layout(title=title, margin=dict(l=20, r=20, t=60, b=20), height=750)
    return fig


# %% Datasets finden + LRU State

def list_nc_files(folder: str) -> list[str]:
    """
    Listet alle .nc-Dateien in einem Ordner auf (vollständige Pfade)
    
    Inputs: folder [str]
    
    Prüft Ordnerexistenz
    Filtert Dateien nach Endung '.nc' (case-insensitive)
    Sortiert die Pfade
    
    Outputs: list [str]
    """
    if not folder or not os.path.isdir(folder):
        return []
    files = []
    for fn in os.listdir(folder):
        if fn.lower().endswith(".nc"):
            files.append(os.path.join(folder, fn))
    return sorted(files)


def _empty_state(reason: str = "keine Daten"):
    """
    Erzeugt einen konsistenten Default-State, wenn kein Dataset geladen werden kann
    
    Inputs: reason [str]
    
    Setzt ok=False und füllt alle erwarteten State-Keys mit leeren DataFrames/Defaults
    
    Outputs: dict: Dashboard-State
    """
    return {
        "ok": False,
        "reason": reason,
        "n": None,
        "years": [],
        "has_mip": False,
        "default_sector": "Sonstige",
        "df_dyn_all": pd.DataFrame(columns=["period", "timestep"]),
        "meta_ts": pd.DataFrame(),
        "timeseries_color_map": {},
        "by_sector_p": {s: pd.DataFrame() for s in SECTORS},
        "by_sector_e": {s: pd.DataFrame() for s in SECTORS},
        "subcarrier_color_map": {},
        "df_life": pd.DataFrame(),
        "df_cost": pd.DataFrame(),
        "df_total_cost": pd.DataFrame(),
        "df_inv_capex": pd.DataFrame(),
        "df_emissions": pd.DataFrame(),
        "df_co2_intensity": pd.DataFrame(),
        "df_lcoe": pd.DataFrame(),
        "df_sector_lcoe": pd.DataFrame(),
        "df_lcos": pd.DataFrame(),
        "df_cashflow": pd.DataFrame(),
        "df_ops_load_metrics": pd.DataFrame(),
        "df_ops_autarky": pd.DataFrame(),
        "df_ops_pv_usage": pd.DataFrame(),
        "df_ops_technology_shares": pd.DataFrame(),
        "project_discount_rate": DEFAULT_DISCOUNT_RATE,
        "has_co2": False,
        "has_ops": False,
        "years_cost": [],
        "has_mip_cost": False,
        "base_period": None,
        "compare_years": [],
        "ts_period_options": [{"label": "Single", "value": "Single"}],
        "default_ts_period": "Single",
        "sank_period_options": [{"label": "Single", "value": "Single"}],
        "default_sank_period": "Single",
        "co2_period_options": [{"label": "Single", "value": "Single"}],
        "default_co2_period": "Single",
        "ops_period_options": [{"label": "Single", "value": "Single"}],
        "default_ops_period": "Single",
    }


def _build_dataset_state(nc_path: str) -> dict:
    """
    Lädt eine .nc-Datei als pypsa.Network und baut alle abgeleiteten Tabellen,
    Farbzuordnungen und UI-Optionen für das Dashboard (State-Object)

    Diese Funktion ist die zentrale Datenpipeline des Dashboards. Alle Module
    greifen später auf die hier vorbereiteten DataFrames und Metadaten zurück.
    
    Inputs: nc_path: str (Pfad zur .nc-Datei)
    
    Validiert Dateipfad; lädt pypsa.Network
    Erzeugt Bus-Taxonomie (ensure_bus_taxonomy)
    Ermittelt MIP-Jahre und has_mip
    Baut Zeitreihen-DF (build_dynamic_timeseries_df), interne Store-Busse, Meta
    (build_timeseries_meta) und Farben
    Erstellt TS-Periodenoptionen aus df_dyn_all['period']
    Baut Lifetime-DF, Leistungen (kW) und Kapazitäten (kWh), expandiert diese auf
    aktive Perioden und bereitet sie nach Sektoren auf
    Sammelt alle Subcarrier und erstellt subcarrier_color_map
    Setzt default_sector anhand verfügbarer Daten
    Erstellt Sankey-Periodenoptionen anhand n.snapshots (MultiIndex/Tuple/Datetime)
    Berechnet Kosten (build_costs_df) und Investitions-CAPEX (build_investment_capex_df)
    Leitet years_cost, has_mip_cost, base_period und compare_years ab
    Gibt State-Dict zurück; Fehler werden abgefangen und in _empty_state resultiert
    
    Outputs: dict: vollständiger Dataset-State
    """
    
    if not nc_path or (not os.path.isfile(nc_path)):
        return _empty_state("Datei nicht gefunden")

    try:
        n = pypsa.Network(nc_path)

        # Taxonomie vorbereiten
        ensure_bus_taxonomy(n)

        years = get_investment_years(n)
        has_mip = bool(getattr(n, "has_investment_periods", False)) and len(years) > 0

        # Zeitreihen
        df_dyn_all = build_dynamic_timeseries_df(n, add_component_prefix=True)
        internal_store_buses = infer_internal_store_buses(n)
        meta_ts = build_timeseries_meta(n, df_dyn_all, internal_store_buses) if not df_dyn_all.empty else pd.DataFrame()
        timeseries_color_map = make_label_color_map(meta_ts.index.tolist() if (meta_ts is not None and not meta_ts.empty) else [])

        # Perioden-Optionen
        if "period" in df_dyn_all.columns:
            periods = sorted(df_dyn_all["period"].dropna().astype(str).unique().tolist())
        else:
            periods = ["Single"]
        ts_period_options = [{"label": p, "value": p} for p in periods] if periods else [{"label": "Single", "value": "Single"}]
        default_ts_period = ts_period_options[0]["value"] if ts_period_options else "Single"

        # Lifetime
        df_life = build_lifetime_table(n)

        # Kapazitäten (kW): aktiv je Periode
        df_caps = build_capacity_table(n)
        df_caps_active = expand_caps_to_active_periods(df_caps, df_life, years, value_col="p_nom")
        by_sector_p, _ = prepare_multicategory(df_caps_active, n, add_component_prefix=True, value_col="p_nom")

        # Energie (kWh): aktiv je Periode
        df_energy = build_energy_capacity_table(n)
        df_energy_active = expand_caps_to_active_periods(df_energy, df_life, years, value_col="e_nom")
        by_sector_e, _ = prepare_multicategory(df_energy_active, n, add_component_prefix=True, value_col="e_nom")

        # Farblogik Subcarrier
        all_subcarriers = _collect_subcarriers(
            by_sector_p,
            by_sector_e,
            df_life,
            meta_ts.reset_index() if (meta_ts is not None and not meta_ts.empty) else None
        )
        subcarrier_color_map = make_subcarrier_color_map(all_subcarriers)

        # Default-Sektor
        available = [
            s for s in SECTORS
            if (s in by_sector_p and by_sector_p[s] is not None and not by_sector_p[s].empty)
            or (s in by_sector_e and by_sector_e[s] is not None and not by_sector_e[s].empty)
        ]
        default_sector = available[0] if available else "Sonstige"

        # Sankey Perioden
        snaps = pd.Index(n.snapshots)

        if isinstance(snaps, pd.MultiIndex):
            periods = sorted(set(snaps.get_level_values(0).astype(str)))

        elif len(snaps) > 0 and isinstance(snaps[0], tuple) and len(snaps[0]) >= 2:
        # pypsa/netcdf: snapshots als Tupel (period, timestamp)
             periods = sorted({str(t[0]) for t in snaps})

        else:
        # Datetime-Snapshots
            dt = pd.to_datetime(snaps, errors="coerce")
            dt = dt[~pd.isna(dt)]
            periods = sorted({str(int(y)) for y in dt.year})

        sank_period_options = [{"label": p, "value": p} for p in periods] if periods else [{"label":"Single","value":"Single"}]
        default_sank_period = sank_period_options[0]["value"]

        # Kosten
        df_cost = build_costs_df(n)
        df_inv_capex = build_investment_capex_df(n)
        df_emissions = build_emissions_df(n)
        df_co2_intensity = build_co2_intensity_scope_df(n, df_emissions)
        co2_costs_in_opex = _co2_costs_already_in_opex_from_network(n)
        df_total_cost = build_total_cost_df(df_cost, df_emissions, co2_costs_in_opex)
        df_lcoe = build_lcoe_df(n, df_cost, df_emissions, co2_costs_in_opex)
        df_sector_lcoe = build_sector_lcoe_df(n, df_cost, df_emissions, co2_costs_in_opex)
        df_lcos = build_lcos_df(n, df_cost, df_emissions, co2_costs_in_opex)
        project_discount_rate = _infer_project_discount_rate(n)
        df_cashflow = build_cashflow_df(n, df_inv_capex, df_total_cost, df_life, years)
        has_co2 = df_emissions is not None and (not df_emissions.empty)

        years_cost = years[:]
        has_mip_cost = has_mip and (df_total_cost is not None) and (not df_total_cost.empty)

        base_period = str(min(years_cost)) if (has_mip_cost and years_cost) else None
        compare_years = [y for y in years_cost if str(y) != str(base_period)] if (has_mip_cost and base_period is not None) else []
        if years:
            co2_period_options = [{"label": str(y), "value": str(y)} for y in years]
            default_co2_period = co2_period_options[0]["value"] if co2_period_options else "Single"
        else:
            co2_period_options = [{"label": "Single", "value": "Single"}]
            default_co2_period = "Single"

        # Betriebsanalyse
        df_ops_load_metrics = build_ops_load_metrics_df(n)
        df_ops_autarky = build_ops_autarky_df(n)
        df_ops_pv_usage = build_ops_pv_usage_df(n)
        df_ops_technology_shares = build_ops_technology_shares_df(n)
        ops_period_values = _ops_period_values(n)
        ops_period_options = [{"label": str(p), "value": str(p)} for p in ops_period_values]
        default_ops_period = ops_period_options[0]["value"] if ops_period_options else "Single"
        has_ops = any(
            df is not None and not df.empty
            for df in [
                df_ops_load_metrics,
                df_ops_autarky,
                df_ops_pv_usage,
                df_ops_technology_shares,
            ]
        )

        return {
            "ok": True,
            "reason": "",
            "n": n,
            "years": years,
            "has_mip": has_mip,
            "default_sector": default_sector,
            "df_dyn_all": df_dyn_all,
            "meta_ts": meta_ts,
            "timeseries_color_map": timeseries_color_map,
            "by_sector_p": by_sector_p,
            "by_sector_e": by_sector_e,
            "subcarrier_color_map": subcarrier_color_map,
            "df_life": df_life,
            "df_cost": df_cost,
            "df_total_cost": df_total_cost,
            "df_inv_capex": df_inv_capex,
            "df_emissions": df_emissions,
            "df_co2_intensity": df_co2_intensity,
            "df_lcoe": df_lcoe,
            "df_sector_lcoe": df_sector_lcoe,
            "df_lcos": df_lcos,
            "df_cashflow": df_cashflow,
            "df_ops_load_metrics": df_ops_load_metrics,
            "df_ops_autarky": df_ops_autarky,
            "df_ops_pv_usage": df_ops_pv_usage,
            "df_ops_technology_shares": df_ops_technology_shares,
            "project_discount_rate": project_discount_rate,
            "co2_costs_in_opex": co2_costs_in_opex,
            "has_co2": has_co2,
            "has_ops": has_ops,
            "years_cost": years_cost,
            "has_mip_cost": has_mip_cost,
            "base_period": base_period,
            "compare_years": compare_years,
            "ts_period_options": ts_period_options,
            "default_ts_period": default_ts_period,
            "sank_period_options": sank_period_options,
            "default_sank_period": default_sank_period,
            "co2_period_options": co2_period_options,
            "default_co2_period": default_co2_period,
            "ops_period_options": ops_period_options,
            "default_ops_period": default_ops_period,
        }

    except Exception as e:
        traceback.print_exc()
        return _empty_state(f"State-Build Fehler: {e!s}")


@lru_cache(maxsize=LRU_CACHE_SIZE)
def get_dataset_state(nc_path: str) -> dict:
    """
    LRU-gecachter Zugriff auf Dataset-States; serialisiert State-Build per globalem Lock
    (Stabilität bei parallelen Dash-Callbacks)
    
    Inputs: nc_path: str
    
    Lock _STATE_BUILD_LOCK hält parallele Builds zurück
    Ruft _build_dataset_state auf; Ergebnis wird durch lru_cache gepuffert
    (maxsize=LRU_CACHE_SIZE)
    
    Outputs: dict: Dataset-State
    """
    with _STATE_BUILD_LOCK:
        return _build_dataset_state(nc_path)


def _get_dataset_mtime_ns(nc_path: str) -> int | None:
    """
    Prüft, wann die .nc-Datei zuletzt geändert wurde.
    
    Inputs: nc_path.
    Outputs: Zahl mit dem Änderungszeitpunkt in Nanosekunden.
    """
    if not nc_path or not os.path.isfile(nc_path):
        return None
    try:
        return os.stat(nc_path).st_mtime_ns
    except OSError:
        return None

# Zwischenspeicher für Datei-Änderungszeiten
_DATASET_MTIME_CACHE: dict[str, int | None] = {}


def get_dataset_state_fresh(nc_path: str) -> dict:
    """
    Prüft ob sich die .nc-Datei seit dem letzten Laden geändert hat.
    Wenn ja, wird der Cache geleert und die Datei neu geladen.
    
    Inputs: nc_path.
    Outputs: Dictionary mit dem aktuellen Dataset-State.
    """
    mtime_ns = _get_dataset_mtime_ns(nc_path)
    prev_mtime_ns = _DATASET_MTIME_CACHE.get(nc_path)
    if prev_mtime_ns != mtime_ns:
        get_dataset_state.cache_clear()
        _DATASET_MTIME_CACHE[nc_path] = mtime_ns
    return get_dataset_state(nc_path)

# Folgende Funktionen laden die verschiedenen Google-Fonts für das Dashboard z.B. Lora und Open Sans.
FONT_STYLESHEET_URL = "https://fonts.googleapis.com/css2?family=Lora:wght@500;600;700&family=Open+Sans:wght@400;600;700&display=swap"
app = Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[FONT_STYLESHEET_URL])
app.index_string = f"""<!DOCTYPE html>
<html>
    <head>
        {{%metas%}}
        <title>{{%title%}}</title>
        {{%favicon%}}
        {{%css%}}
        <style>
{GLOBAL_DASHBOARD_CSS}
        </style>
    </head>
    <body>
        {{%app_entry%}}
        <script>
        (function() {{
            const MIN_TOP = 190;
            const GAP = 8;
            let scheduled = false;

            function updateFilterSidebarTop() {{
                scheduled = false;
                const tabs = document.getElementById("main-tabs");
                let nextTop = MIN_TOP;
                if (tabs) {{
                    const rect = tabs.getBoundingClientRect();
                    if (Number.isFinite(rect.bottom)) {{
                        nextTop = Math.max(MIN_TOP, Math.ceil(rect.bottom + GAP));
                    }}
                }}
                document.documentElement.style.setProperty("--filter-sidebar-top", nextTop + "px");
            }}

            function scheduleUpdate() {{
                if (scheduled) {{
                    return;
                }}
                scheduled = true;
                window.requestAnimationFrame(updateFilterSidebarTop);
            }}

            function startFilterSidebarObserver() {{
                if (document.body) {{
                    const observer = new MutationObserver(scheduleUpdate);
                    observer.observe(document.body, {{
                        attributes: true,
                        childList: true,
                        subtree: true
                    }});
                }}
                scheduleUpdate();
            }}

            window.addEventListener("load", scheduleUpdate);
            window.addEventListener("resize", scheduleUpdate);
            window.addEventListener("scroll", scheduleUpdate, {{ passive: true }});
            document.addEventListener("click", function() {{
                window.setTimeout(scheduleUpdate, 0);
                window.setTimeout(scheduleUpdate, 250);
            }}, true);

            if (document.readyState === "loading") {{
                document.addEventListener("DOMContentLoaded", startFilterSidebarObserver);
            }} else {{
                startFilterSidebarObserver();
            }}
        }})();
        </script>
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>"""


#%% Report-Export

# Der PDF-Export nutzt dieselben vorbereiteten State-Objekte wie die Dashboard-Oberfläche.
REPORT_MARGIN_LEFT_MM = 24.1
REPORT_MARGIN_RIGHT_MM = 20.0
REPORT_MARGIN_TOP_MM = 20.0
REPORT_MARGIN_BOTTOM_MM = 20.0
REPORT_FALLBACK_OUTPUT_DIR = os.path.join(BASE_DIR, "reports")

def _report_prepare_dir(path: str) -> str:
    """
    Legt den Ausgabeordner für den PDF-Bericht an, falls er noch nicht vorhanden ist, und gibt den Pfad zurück.
    
    Inputs: path.
    Outputs: Ordnerpfad als String.
    """
    os.makedirs(path, exist_ok=True)
    return path


def _report_default_output_dir() -> str:
    """
    Bestimmt, wohin der PDF-Bericht standardmäßig gespeichert werden soll.
    
    Inputs: keine expliziten Parameter.
    Outputs: Ordnerpfad als String.
    """
    user_home = os.path.expanduser("~")
    downloads_dir = os.path.join(user_home, "Downloads")
    if os.path.isdir(downloads_dir):
        return downloads_dir
    if os.path.isdir(user_home):
        return user_home
    return _report_prepare_dir(REPORT_FALLBACK_OUTPUT_DIR)


def _report_output_candidates() -> list[str]:
    """
    Erstellt eine Liste von Ordnern, in denen der PDF-Bericht gespeichert werden könnte.
    
    Inputs: keine expliziten Parameter.
    Outputs: Liste mit möglichen Ausgabeordnern.
    """
    candidates = []
    default_dir = _report_default_output_dir()
    if default_dir:
        candidates.append(default_dir)
    if REPORT_FALLBACK_OUTPUT_DIR not in candidates:
        candidates.append(REPORT_FALLBACK_OUTPUT_DIR)
    return candidates


def _report_save_pdf_to_disk(pdf_bytes: bytes, filename: str) -> tuple[str, str]:
    """
    Speichert die erzeugte PDF-Datei auf der Festplatte.
    
    Inputs: pdf_bytes, filename.
    Outputs: Abgelegte PDF-Datei.
    """
    errors = []
    for output_dir in _report_output_candidates():
        try:
            output_dir = _report_prepare_dir(output_dir)
            output_path = os.path.join(output_dir, filename)
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
            fallback_dir = os.path.abspath(_report_prepare_dir(REPORT_FALLBACK_OUTPUT_DIR))
            if os.path.abspath(output_dir) == fallback_dir:
                return output_path, "fallback"
            return output_path, "downloads"
        except Exception as exc:
            errors.append(f"{output_dir}: {exc}")
    raise RuntimeError(" ; ".join(errors) if errors else "Kein gültiger Ausgabeordner verfügbar.")


def _report_available_periods(st: dict) -> list[str]:
    """
    Sammelt alle Perioden, die für den PDF-Bericht verfügbar sind.
    
    Inputs: Dashboard-State
    Outputs: Liste mit verfügbaren Perioden als Text.
    """
    if not st.get("has_mip", False):
        return ["Single"]

    candidates: list[str] = []
    candidates.extend(str(y) for y in st.get("years", []))
    candidates.extend(str(y) for y in st.get("years_cost", []))
    for options_key in ("ops_period_options", "co2_period_options", "sank_period_options", "ts_period_options"):
        for option in st.get(options_key, []):
            if isinstance(option, dict) and ("value" in option):
                candidates.append(str(option["value"]))

    periods = _unique_preserve(candidates)
    return periods or ["Single"]


def _report_available_export_sectors(st: dict) -> list[str]:
    """
    Prüft, welche Sektoren im PDF-Bericht wirklich exportiert werden können.
    
    Inputs: Dashboard-State
    Outputs: Liste mit verfügbaren Sektoren.
    """
    available = []
    df_sector_lcoe = st.get("df_sector_lcoe", pd.DataFrame())
    df_emissions = st.get("df_emissions", pd.DataFrame())
    df_ops_shares = st.get("df_ops_technology_shares", pd.DataFrame())

    for sector in SECTORS:
        has_capacity = (
            (sector in st.get("by_sector_p", {}) and st["by_sector_p"].get(sector) is not None and not st["by_sector_p"].get(sector).empty)
            or (sector in st.get("by_sector_e", {}) and st["by_sector_e"].get(sector) is not None and not st["by_sector_e"].get(sector).empty)
        )
        has_lcoe = (
            not df_sector_lcoe.empty
            and "sector" in df_sector_lcoe.columns
            and df_sector_lcoe["sector"].astype(str).eq(sector).any()
        )
        has_emissions = (
            not df_emissions.empty
            and "sector" in df_emissions.columns
            and df_emissions["sector"].astype(str).eq(sector).any()
        )
        has_ops = (
            not df_ops_shares.empty
            and "sector" in df_ops_shares.columns
            and df_ops_shares["sector"].astype(str).eq(sector).any()
        )
        if has_capacity or has_lcoe or has_emissions or has_ops:
            available.append(sector)

    return available or SECTORS[:]


def _report_validate_export_periods(st: dict, mode, values) -> list[str]:
    """
    Prüft, welche Perioden für den PDF-Export wirklich verwendet werden dürfen.
    
    Inputs: st, mode, values.
    Outputs: Liste gültiger Perioden als Text.
    """
    available = _report_available_periods(st)
    if str(mode) != "specific":
        return available
    selected = [str(v) for v in (values or []) if str(v) in set(available)]
    return _unique_preserve(selected)


def _report_validate_export_sectors(st: dict, mode, values) -> list[str]:
    """
    Hilfsfunktion für den PDF-Bericht: bereitet report validate export sectors auf.
    
    Inputs: st, mode, values.
    Outputs: berechneter Rückgabewert gemäß Funktionslogik.
    """
    available = _report_available_export_sectors(st)
    if str(mode) != "specific":
        return available
    selected = [str(v) for v in (values or []) if str(v) in set(available)]
    return _unique_preserve(selected)


def _report_filter_period(df: pd.DataFrame, period_value) -> pd.DataFrame:
    """
    Filtert eine Tabelle für den PDF-Bericht auf eine bestimmte Periode.
    
    Inputs: df, period_value.
    Outputs: DataFrame mit nur den Zeilen dieser Periode.
    """
    if df is None or df.empty or "period" not in df.columns:
        return pd.DataFrame()
    return df[df["period"].astype(str) == str(period_value)].copy()


def _report_filter_periods(df: pd.DataFrame, periods, col: str = "period") -> pd.DataFrame:
    """
    Filtert eine Tabelle auf mehrere ausgewählte Perioden.
    
    Inputs: df, periods, col.
    Outputs: Gefilterter DataFrame.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    if not periods or col not in df.columns:
        return df.copy()
    allowed = {str(v) for v in periods}
    return df[df[col].astype(str).isin(allowed)].copy()


def _report_first_period_row(df: pd.DataFrame, period_value):
    """
    Sucht im DataFrame nach der ausgewählten Periode und gibt die erste passende Zeile zurück.
    Da der PDF-Bericht an manchen Stellen genau einen einzelnen Wert für eine Periode braucht.
    
    Inputs: df, period_value.
    Outputs: Einzelne Tabellenzeile.
    """
    d = _report_filter_period(df, period_value)
    if d.empty:
        return None
    return d.iloc[0]


def _report_safe_float(value) -> float | None:
    """
    Wandelt eine Zahl in eine gültige Kommazahl um.
    
    Inputs: value.
    Outputs: Gültige float-Zahl.
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return out


def _report_format_number(value, digits: int = 1) -> str:
    """
    Macht aus einer Zahl einen Zahlen-Text für den PDF-Bericht in deutscher Schreibweise.
    
    Inputs: value, digits.
    Outputs: Formatierter Text.
    """
    number = _report_safe_float(value)
    if number is None:
        return "-"
    text = f"{number:,.{digits}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _report_format_currency_per_year(value) -> str:
    """
    Formatiert einen Zahlenwert als jährliche Kostenangabe für den PDF-Bericht.
    
    Inputs: value.
    Outputs: Formatierter Text mit Einheit EUR/Jahr.
    """
    number = _report_safe_float(value)
    if number is None:
        return "-"
    return f"{_report_format_number(number, 0)} EUR/Jahr"


def _report_format_currency_once(value) -> str:
    """
    Formatiert einen Zahlenwert als einmaligen Euro-Betrag für den PDF-Bericht.
    
    Inputs: value.
    Outputs: Formatierter Text mit Einheit EUR.
    """
    number = _report_safe_float(value)
    if number is None:
        return "-"
    return f"{_report_format_number(number, 0)} EUR"


def _report_format_power(value) -> str:
    """
    Formatiert einen Zahlenwert als Leistung für den PDF-Bericht.
    
    Inputs: value.
    Outputs: Formatierter Text mit Einheit kW.
    """
    number = _report_safe_float(value)
    if number is None:
        return "-"
    return f"{_report_format_number(number, 0)} kW"


def _report_format_energy(value) -> str:
    """
    Formatiert einen Zahlenwert als Energiemenge für den PDF-Bericht.
    
    Inputs: value.
    Outputs: Formatierter Text mit Einheit kWh.
    """
    number = _report_safe_float(value)
    if number is None:
        return "-"
    return f"{_report_format_number(number, 0)} kWh"


def _report_format_emissions(value) -> str:
    """
    Formatiert einen Zahlenwert als jährliche CO2-Emission für den PDF-Bericht.
    
    Inputs: value.
    Outputs: Formatierter Text mit Einheit t CO2/a.
    """
    number = _report_safe_float(value)
    if number is None:
        return "-"
    return f"{_report_format_number(number, 1)} t CO2/a"


def _report_format_co2_price(value) -> str:
    """
    Formatiert einen Zahlenwert als CO2-Preis für den PDF-Bericht.
    
    Inputs: value.
    Outputs: Formatierter Text mit Einheit EUR/t.
    """
    number = _report_safe_float(value)
    if number is None:
        return "-"
    return f"{_report_format_number(number, 0)} EUR/t"


def _report_format_percent(value, digits: int = 1) -> str:
    """
    Formatiert einen Zahlenwert als Prozentwert für den PDF-Bericht.
    
    Inputs: value, digits.
    Outputs: Formatierter Text mit Prozentzeichen.
    """
    number = _report_safe_float(value)
    if number is None:
        return "-"
    return f"{_report_format_number(number, digits)} %"


def _report_format_lcoe(value) -> str:
    """
    Formatiert einen Zahlenwert als Strom- oder Energiegestehungskosten für den PDF-Bericht.
    
    Inputs: value.
    Outputs: Formatierter Text mit Einheit ct/kWh.
    """
    number = _report_safe_float(value)
    if number is None:
        return "-"
    return f"{_report_format_number(number, 2)} ct/kWh"


def _report_pretty_label(value) -> str:
    """
    Erzeugt aus technischen Komponentenlabeln einen Namen für den PDF-Bericht.
    
    Inputs: value.
    Outputs: Lesbarer Anzeigename als Text.
    """
    if value is None:
        return "-"
    text = strip_variable_suffix(str(value))
    text = strip_prefix(text)
    text = text.replace("_", " ").strip()
    return text or "-"


def _report_scope_label(periods: list[str]) -> str:
    """
    Erstellt einen lesbaren Text, der beschreibt, welche Perioden im PDF-Bericht enthalten sind.
    
    Inputs: periods.
    Outputs: Kurzer Beschreibungstext für den Berichtsumfang.
    """
    if not periods:
        return "keine Periodenauswahl"
    if periods == ["Single"]:
        return "Einjahresanalyse"
    if len(periods) == 1:
        return f"Periode {periods[0]}"
    preview = ", ".join(periods[:4])
    if len(periods) > 4:
        preview += ", ..."
    return f"{len(periods)} Perioden ({preview})"


def _report_has_positive_values(df: pd.DataFrame, value_col: str) -> bool:
    """
    Prüft, ob eine Tabelle in einer bestimmten Spalte überhaupt nennenswerte Größen enthält.
    
    Inputs: df, value_col.
    Outputs: True oder False.
    """
    if df is None or df.empty or value_col not in df.columns:
        return False
    values = pd.to_numeric(df[value_col], errors="coerce").fillna(0.0)
    return bool((values.abs() > 1e-9).any())


def _report_attach_sector_columns(
    n: pypsa.Network | None,
    df: pd.DataFrame,
    component_col: str = "component",
    name_col: str = "name",
) -> pd.DataFrame:
    """
    Ergänzt in einer Berichtstabelle die Zuordnung zu Sektor und Subcarrier.
    
    Inputs: n, df, component_col, name_col.
    Outputs: DataFrame mit den zusätzlichen Spalten sector und subcarrier.
    """
    if n is None or df is None or df.empty or component_col not in df.columns or name_col not in df.columns:
        return pd.DataFrame() if df is None else df.copy()

    out = df.copy()
    if "sector" in out.columns and "subcarrier" in out.columns:
        return out

    lookup: dict[tuple[str, str], tuple[str, str]] = {}
    sectors = []
    subcarriers = []

    for _, row in out.iterrows():
        comp = str(row.get(component_col, "") or "")
        name = str(row.get(name_col, "") or "")
        key = (comp, name)
        if key not in lookup:
            sector_value, subcarrier_value = ("Sonstige", DEFAULT_SUBCARRIER)
            static_df = getattr(n, comp, None) if comp else None
            if static_df is not None and hasattr(static_df, "index") and name in static_df.index:
                static_row = static_df.loc[name]
                sector_value, subcarrier_value = sector_subcarrier_from_component_row(n, comp, static_row)
            lookup[key] = (sector_value, subcarrier_value)
        sector_value, subcarrier_value = lookup[key]
        sectors.append(sector_value)
        subcarriers.append(subcarrier_value)

    out["sector"] = sectors
    out["subcarrier"] = subcarriers
    return out


def _report_pil_font(size: int = 14, bold: bool = False):
    """
    Sucht eine passende Schriftart für den PDF-Bericht.
    
    Inputs: size, bold.
    Outputs: PIL-Schriftobjekt.
    """
    from PIL import ImageFont

    candidates = []
    if bold:
        candidates.extend([
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\ARIALBD.TTF",
            r"C:\Windows\Fonts\DejaVuSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\ARIAL.TTF",
            r"C:\Windows\Fonts\DejaVuSans.ttf",
        ])

    for path in candidates:
        try:
            if os.path.isfile(path):
                return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _report_pil_text_size(draw, text: str, font) -> tuple[int, int]:
    """
    Misst, wie viel Platz ein Text in Pixeln braucht, um das Layout einzuhalten.
    
    Inputs: draw, text, font.
    Outputs: Tuple mit Breite und Höhe.
    """
    bbox = draw.textbbox((0, 0), str(text), font=font)
    return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])


def _report_pil_fit_text(draw, text: str, max_width: int, font) -> str:
    """
    Sorgt dafür, dass ein Text in seiner Breite begrenzt wird.
    
    Inputs: draw, text, max_width, font.
    Outputs: Gekürzter oder unveränderter Text.
    """
    text = str(text)
    w, _ = _report_pil_text_size(draw, text, font)
    if w <= max_width:
        return text
    ell = "..."
    lo, hi = 0, len(text)
    best = ell
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip() + ell
        cw, _ = _report_pil_text_size(draw, candidate, font)
        if cw <= max_width:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _report_pil_bytes(width: int, height: int, draw_fn, _label: str) -> bytes | None:
    """
    Erzeugt mit Python Imaging Library ein Bild und gibt es als PNG-Bytes für den PDF-Bericht zurück.
    
    Inputs: width, height, draw_fn, _label.
    Outputs: PNG-Bild als bytes.
    """
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        draw_fn(img, draw)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def _report_pil_draw_title(draw, title: str, x: int, y: int, width: int) -> int:
    """
    Erzeugt eine Überschrift auf ein Bild und bestimmt danach, wo die nächste Zeile anfangen soll.
    
    Inputs: draw, title, x, y, width.
    Outputs: Neue y-Position als Zahl.
    """
    title_font = _report_pil_font(24, bold=True)
    text = _report_pil_fit_text(draw, title, width, title_font)
    draw.text((x, y), text, fill="#0f3554", font=title_font)
    _, h = _report_pil_text_size(draw, text, title_font)
    return y + h + 10


def _report_pil_draw_legend(draw, labels: list[str], colors: list[str], x: int, y: int, width: int) -> int:
    """
    Erzeugt eine Legende auf ein Bild und bestimmt danach, wo die nächste Zeile anfangen soll.
    
    Inputs: draw, labels, colors, x, y, width.
    Outputs: Neue y-Position als Zahl.
    """
    font = _report_pil_font(13, bold=False)
    cursor_x = x
    cursor_y = y
    line_h = 20
    for label, color in zip(labels, colors):
        text = str(label)
        tw, th = _report_pil_text_size(draw, text, font)
        block_w = 16 + 8 + tw + 18
        if cursor_x + block_w > x + width:
            cursor_x = x
            cursor_y += line_h + 6
        draw.rectangle((cursor_x, cursor_y + 2, cursor_x + 12, cursor_y + 14), fill=color, outline=color)
        draw.text((cursor_x + 18, cursor_y), text, fill="#334155", font=font)
        cursor_x += block_w
    return cursor_y + line_h + 8


def _report_normalize_color(value, default: str | None = None) -> str | None:
    """
    Erzeugt aus verschiedenen Farbangaben ein einheitliches Farbformat für den PDF-Bericht.
    
    Inputs: value, default.
    Outputs: Normalisierter Farbwert.
    """
    if value is None:
        return default
    try:
        text = str(value).strip()
    except Exception:
        return default
    if not text or text.lower() == "nan":
        return default

    m = re.match(
        r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*([0-9]*\.?[0-9]+))?\s*\)$",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        r = max(0, min(255, int(m.group(1))))
        g = max(0, min(255, int(m.group(2))))
        b = max(0, min(255, int(m.group(3))))
        if m.group(4) is not None:
            try:
                a = max(0.0, min(1.0, float(m.group(4))))
            except ValueError:
                a = 1.0
        else:
            a = 1.0
        return f"#{r:02x}{g:02x}{b:02x}" if a >= 0.999 else (r / 255.0, g / 255.0, b / 255.0, a)

    try:
        import matplotlib.colors as mcolors
        rgba = mcolors.to_rgba(text)
        return mcolors.to_hex(rgba, keep_alpha=(rgba[3] < 0.999))
    except Exception:
        return default


def _report_palette(keys: list[str], preferred: dict[str, str] | None = None) -> dict[str, str]:
    """
    Erstellt eine Farbpalette für Diagramme oder PDF-Grafiken.
    
    Inputs: keys, preferred.
    Outputs: Farbpalette.
    """
    base = [
        "#0f3554", "#2a9d8f", "#e76f51", "#457b9d", "#f4a261",
        "#8d99ae", "#6d597a", "#84a59d", "#bc4749", "#3a86ff",
        "#588157", "#ff006e",
    ]
    out = {}
    for idx, key in enumerate(keys):
        fallback = base[idx % len(base)]
        preferred_color = preferred.get(key) if preferred and key in preferred else None
        out[key] = _report_normalize_color(preferred_color, default=fallback) or fallback
    return out


def _report_mpl_capacity_scope_bytes(
    df_scope: pd.DataFrame,
    title: str,
    value_col: str,
    unit: str,
    period_order: list[str],
    sector_order: list[str],
    color_map: dict[str, str] | None = None,
) -> bytes | None:
    """
    Baut die Grafik für den PDF-Bericht.
    
    Inputs: df_scope, title, value_col, unit, period_order, sector_order, color_map.
    Outputs: PNG-Bild als bytes.
    """
    if df_scope is None or df_scope.empty or value_col not in df_scope.columns:
        return None

    d = df_scope.copy()
    d[value_col] = pd.to_numeric(d[value_col], errors="coerce").fillna(0.0)
    d = d[d[value_col] > 1e-9].copy()
    if d.empty:
        return None

    d["row_label"] = d.apply(
        lambda row: f"{row['period']} | {row['sector']}" if str(row.get("period", "Single")) != "Single" else str(row.get("sector", "-")),
        axis=1,
    )

    desired_order = []
    for period in period_order:
        for sector in sector_order:
            desired_order.append(f"{period} | {sector}" if str(period) != "Single" else str(sector))

    pivot = d.groupby(["row_label", "subcarrier"], dropna=False)[value_col].sum().unstack(fill_value=0.0)
    ordered_rows = [label for label in desired_order if label in pivot.index]
    ordered_rows.extend([label for label in pivot.index.tolist() if label not in ordered_rows])
    pivot = pivot.reindex(ordered_rows).fillna(0.0)
    pivot = pivot.loc[pivot.sum(axis=1) > 1e-9]
    if pivot.empty:
        return None

    subcarrier_order = pivot.sum(axis=0).sort_values(ascending=False).index.tolist()
    palette = _report_palette([str(v) for v in subcarrier_order], color_map)
    width = 1240
    height = max(430, 175 + 48 * len(pivot.index))
    max_total = float(pivot.sum(axis=1).max()) if not pivot.empty else 0.0
    if max_total <= 0.0:
        return None

    def _draw(_img, draw):
        title_y = _report_pil_draw_title(draw, title, 36, 24, width - 72)
        legend_y = _report_pil_draw_legend(
            draw,
            [str(v) for v in subcarrier_order],
            [palette.get(str(v), "#999999") for v in subcarrier_order],
            36,
            title_y,
            width - 72,
        )
        chart_left = 260
        chart_right = width - 48
        chart_top = legend_y + 12
        chart_bottom = height - 55
        chart_width = chart_right - chart_left
        row_h = max(26, int((chart_bottom - chart_top) / max(1, len(pivot.index))))
        font = _report_pil_font(13)
        small_font = _report_pil_font(12)

        for tick in range(5):
            x = chart_left + tick * chart_width / 4
            draw.line((x, chart_top, x, chart_bottom), fill="#e2e8f0", width=1)
            tick_val = max_total * tick / 4
            txt = _report_format_number(tick_val, 0)
            tw, _ = _report_pil_text_size(draw, txt, small_font)
            draw.text((x - tw / 2, chart_bottom + 8), txt, fill="#64748b", font=small_font)

        for idx, item in enumerate(pivot.index.tolist()):
            y = chart_top + idx * row_h + 4
            label = _report_pil_fit_text(draw, item, chart_left - 62, font)
            _, th = _report_pil_text_size(draw, label, font)
            draw.text((36, y + max(0, (18 - th) / 2)), label, fill="#334155", font=font)

            left = chart_left
            total = 0.0
            for subcarrier in subcarrier_order:
                value = float(pivot.at[item, subcarrier])
                if value <= 0.0:
                    continue
                bar_w = int(chart_width * value / max_total)
                color = palette.get(str(subcarrier), "#999999")
                draw.rectangle((left, y, left + bar_w, y + 18), fill=color, outline=color)
                left += bar_w
                total += value

            total_txt = f"{_report_format_number(total, 0)} {unit}"
            tw, th_txt = _report_pil_text_size(draw, total_txt, small_font)
            pad_x = 6
            pad_y = 2
            box_w = tw + 2 * pad_x
            box_h = th_txt + 2 * pad_y
            box_y0 = y + max(0, (18 - box_h) / 2)
            box_y1 = box_y0 + box_h

            outside_x = left + 10
            if outside_x + box_w <= chart_right:
                box_x0 = outside_x
                box_x1 = outside_x + box_w
            else:
                box_x1 = max(chart_left + box_w, left - 6)
                box_x0 = max(chart_left + 2, box_x1 - box_w)
                box_x1 = box_x0 + box_w

            if hasattr(draw, "rounded_rectangle"):
                draw.rounded_rectangle(
                    (box_x0, box_y0, box_x1, box_y1),
                    radius=6,
                    fill="#ffffff",
                    outline="#cbd5e1",
                    width=1,
                )
            else:
                draw.rectangle(
                    (box_x0, box_y0, box_x1, box_y1),
                    fill="#ffffff",
                    outline="#cbd5e1",
                    width=1,
                )
            draw.text((box_x0 + pad_x, box_y0 + pad_y - 1), total_txt, fill="#0f172a", font=small_font)

        draw.line((chart_left, chart_bottom, chart_right, chart_bottom), fill="#94a3b8", width=2)

    return _report_pil_bytes(width, height, _draw, title)


def _report_validate_map_components(st: dict, values) -> list[str]:
    """
    Prüft, ob ausgewählte Kartenkomponenten wirklich im aktuellen Netzwerk existieren.
    
    Inputs: st, values.
    Outputs: Liste mit Komponenten-IDs.
    """
    if not values:
        return []
    df_map = build_map_component_table(st.get("n")) if st.get("n") is not None else pd.DataFrame()
    if df_map.empty or "component_id" not in df_map.columns:
        return []
    valid_ids = set(df_map["component_id"].astype(str))
    out = []
    for value in values:
        value_str = str(value)
        if value_str in valid_ids:
            out.append(value_str)
    return out


def _report_map_filtered_df(st: dict, selections: dict) -> pd.DataFrame:
    """
    Erstellt die Kartentabelle, die später im PDF-Bericht verwendet wird, und filtert sie nach den Berichtseinstellungen.
    
    Inputs: st, selections.
    Outputs: DataFrame mit Kartenkomponenten.
    """
    n = st.get("n")
    if n is None:
        return pd.DataFrame()
    df_map = build_map_component_table(n)
    if df_map.empty:
        return df_map

    export_periods = [str(v) for v in (selections.get("export_periods") or [])]
    if export_periods and export_periods != ["Single"]:
        frames = []
        for period in export_periods:
            d_period = filter_map_components_for_period(df_map, st.get("df_life", pd.DataFrame()), period)
            if not d_period.empty:
                frames.append(d_period)
        if frames:
            df_map = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["component_id"])
        else:
            df_map = df_map.iloc[0:0].copy()
    else:
        map_period = selections.get("map_period", "all")
        df_map = filter_map_components_for_period(df_map, st.get("df_life", pd.DataFrame()), map_period)

    selected_sectors = {str(v) for v in (selections.get("export_sectors") or [])}
    if selected_sectors and "sector" in df_map.columns:
        df_map = df_map[df_map["sector"].astype(str).isin(selected_sectors)].copy()

    selected_components = {str(v) for v in (selections.get("map_components") or [])}
    if selected_components:
        df_map = df_map[df_map["component_id"].astype(str).isin(selected_components)].copy()
    return df_map


def _report_map_collapse_period_variants(df_map: pd.DataFrame) -> pd.DataFrame:
    """
    Fasst mehrere Kartenpunkte zusammen, wenn sie fachlich und räumlich zur selben Komponente gehören.
    
    Inputs: df_map.
    Outputs: Kartentabelle, Markerinformation oder Kartenlayout.
    """
    if df_map is None or df_map.empty:
        return pd.DataFrame()

    d = df_map.copy()
    d["_group_lon"] = pd.to_numeric(d.get("lon"), errors="coerce").round(7)
    d["_group_lat"] = pd.to_numeric(d.get("lat"), errors="coerce").round(7)
    d["_group_base"] = d.get("base_display_name", d.get("display_name", "")).astype(str).str.strip()
    d.loc[d["_group_base"].eq(""), "_group_base"] = d.get("layer_label", "").astype(str)

    rows = []
    for _, group in d.groupby(["map_layer_key", "_group_base", "_group_lon", "_group_lat"], sort=False, dropna=False):
        group = _map_sort_group_for_hover(group)
        first = group.iloc[0].copy()
        build_years = [
            str(value).strip()
            for value in group.get("build_year", pd.Series(dtype=str)).tolist()
            if str(value).strip() not in ("", "nan")
        ]
        first["component_id"] = "map_export|" + "|".join(group["component_id"].astype(str).tolist())
        first["component"] = _join_unique_text(group["component"].tolist(), fallback=str(first.get("component", "")))
        first["name"] = _join_unique_text(group["name"].tolist(), fallback=str(first.get("name", "")))
        first["base_name"] = _join_unique_text(group["base_name"].tolist(), fallback=str(first.get("base_name", "")))
        first["display_name"] = _text_or_default(first.get("base_display_name"), _text_or_default(first.get("display_name"), "Komponente"))
        first["base_display_name"] = first["display_name"]
        first["build_year"] = ", ".join(_unique_preserve(build_years))
        first["sector"] = _join_unique_text(group["sector"].tolist(), fallback=str(first.get("sector", "")))
        first["subcarrier"] = _join_unique_text(group["subcarrier"].tolist(), fallback=str(first.get("subcarrier", "")))
        first["connection_buses"] = _unique_preserve(
            bus for buses in group["connection_buses"].tolist() for bus in (buses if isinstance(buses, list) else [])
        )
        first["bus_summary"] = _join_unique_text(group["connection_buses"].tolist())
        first["capacity"] = _map_group_capacity_summary(group)
        first["source"] = _join_unique_text(group["source"].tolist(), fallback=str(first.get("source", "")))
        first["accuracy_m"] = _join_unique_text(group["accuracy_m"].tolist(), fallback=str(first.get("accuracy_m", "")))
        first["crs"] = _join_unique_text(group["crs"].tolist(), fallback=str(first.get("crs", MAP_CRS_EPSG)))
        first["coordinate_epoch"] = _join_unique_text(
            group["coordinate_epoch"].tolist(),
            fallback=str(first.get("coordinate_epoch", "")),
        )
        first["component_count"] = 1
        first["component_details"] = "<br>".join(group.apply(_map_detail_line, axis=1).tolist())
        first["marker_size"] = int(pd.to_numeric(group["marker_size"], errors="coerce").fillna(12).max())
        first = first.drop(labels=[c for c in ("_group_lon", "_group_lat", "_group_base") if c in first.index])
        rows.append(first)

    return pd.DataFrame(rows)


def _report_unique_join(values, max_items: int = 4) -> str:
    """
    Erstellt aus mehreren Werten eine kurze, saubere Textliste.
    
    Inputs: values, max_items.
    Outputs: Text mit eindeutigen Einträgen.
    """
    out = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if not text or text.lower() == "nan" or text in seen:
            continue
        seen.add(text)
        out.append(text)
    if not out:
        return "-"
    if len(out) <= max_items:
        return ", ".join(out)
    return ", ".join(out[:max_items]) + f" (+{len(out) - max_items})"


def _report_map_overview_rows(df_map: pd.DataFrame, df_plot: pd.DataFrame, map_period) -> list[tuple[str, str]]:
    """
    Erstellt kurze Übersichtsinformationen zur Karte für den PDF-Bericht.
    
    Inputs: df_map, df_plot, map_period.
    Outputs: Liste der Übersichtsinformationen.
    """
    if df_map is None or df_map.empty:
        return []
    crs = _report_unique_join(df_map.get("crs", pd.Series(dtype=str)).tolist(), max_items=2)
    sources = _report_unique_join(df_map.get("source", pd.Series(dtype=str)).tolist(), max_items=2)
    sectors = _report_unique_join(df_map.get("sector", pd.Series(dtype=str)).tolist(), max_items=3)

    accuracy_text = "-"
    if "accuracy_m" in df_map.columns:
        accuracy = pd.to_numeric(df_map["accuracy_m"], errors="coerce").dropna()
        if not accuracy.empty:
            accuracy_text = f"Median { _report_format_number(float(accuracy.median()), 0) } m"

    if isinstance(map_period, (list, tuple, set)):
        map_scope_text = f"Exportumfang: {_report_scope_label([str(v) for v in map_period])}"
    elif str(map_period) == "all":
        map_scope_text = "Alle aktiven Komponenten"
    else:
        map_scope_text = f"Aktive Komponenten der Periode {map_period}"

    rows = [
        ("Kartensicht", map_scope_text),
        ("Georeferenzierte Anlagen", _report_format_number(len(df_map), 0)),
        ("Sektoren", sectors),
        ("Koordinatenreferenzsystem", crs),
        ("Lagequelle", sources),
        ("Lagegenauigkeit", accuracy_text),
    ]
    return rows


def _report_web_mercator_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """
    rechnet geografische Koordinaten (Längengrad / Breitengrad) in Karten-Pixelkoordinaten um.
    
    Inputs: lon, lat, zoom.
    Outputs: Berechnete Pixelkoordinaten.
    """
    lat_clamped = max(min(float(lat), 85.05112878), -85.05112878)
    lon_value = float(lon)
    scale = 256.0 * (2 ** int(zoom))
    x = (lon_value + 180.0) / 360.0 * scale
    lat_rad = math.radians(lat_clamped)
    y = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * scale
    return x, y


def _report_osm_basemap_image(
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    zoom: int,
):
    """
    Lädt aus OpenStreetMap eine Karten-Hintergrundgrafik für einen bestimmten Kartenausschnitt.
    
    Inputs: lon_min, lon_max, lat_min, lat_max, zoom.
    Outputs: PIL-Bildobjekt der OpenStreetMap-Hintergrundkarte.
    """
    try:
        from PIL import Image
        import ssl
        from urllib.request import Request, urlopen
    except Exception:
        return None

    try:
        import certifi
        ssl_contexts = [ssl.create_default_context(cafile=certifi.where())]
    except Exception:
        ssl_contexts = []
    try:
        ssl_contexts.append(ssl.create_default_context())
    except Exception:
        pass
    try:
        ssl_contexts.append(ssl._create_unverified_context())
    except Exception:
        pass

    x_left, y_bottom = _report_web_mercator_pixel(lon_min, lat_min, zoom)
    x_right, y_top = _report_web_mercator_pixel(lon_max, lat_max, zoom)
    if x_right < x_left:
        x_left, x_right = x_right, x_left
    if y_bottom < y_top:
        y_top, y_bottom = y_bottom, y_top

    tile_x_min = int(math.floor(x_left / 256.0))
    tile_x_max = int(math.floor(x_right / 256.0))
    tile_y_min = int(math.floor(y_top / 256.0))
    tile_y_max = int(math.floor(y_bottom / 256.0))

    num_tiles = max(0, tile_x_max - tile_x_min + 1) * max(0, tile_y_max - tile_y_min + 1)
    if num_tiles <= 0 or num_tiles > 64:
        return None

    mosaic = Image.new("RGB", ((tile_x_max - tile_x_min + 1) * 256, (tile_y_max - tile_y_min + 1) * 256), "#f3f4f6")
    loaded_tiles = 0
    tile_url_templates = [
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
    ]

    def _fetch_tile(tile_x_wrapped: int, tile_y: int):
        headers = {
            "User-Agent": "PyPSA-Dashboard-Report/1.0 (+https://www.openstreetmap.org/)",
            "Referer": "https://www.openstreetmap.org/",
            "Accept": "image/png,image/*;q=0.9,*/*;q=0.5",
        }
        for url_template in tile_url_templates:
            url = url_template.format(z=zoom, x=tile_x_wrapped, y=tile_y)
            for ssl_context in ssl_contexts or [None]:
                try:
                    request = Request(url, headers=headers)
                    kwargs = {"timeout": 8}
                    if ssl_context is not None:
                        kwargs["context"] = ssl_context
                    with urlopen(request, **kwargs) as response:
                        tile_bytes = response.read()
                    return Image.open(io.BytesIO(tile_bytes)).convert("RGB")
                except Exception:
                    continue
        return None

    for tile_x in range(tile_x_min, tile_x_max + 1):
        for tile_y in range(tile_y_min, tile_y_max + 1):
            if tile_y < 0 or tile_y >= (2 ** zoom):
                continue
            tile_x_wrapped = tile_x % (2 ** zoom)
            try:
                tile_img = _fetch_tile(tile_x_wrapped, tile_y)
                if tile_img is None:
                    continue
                mosaic.paste(tile_img, ((tile_x - tile_x_min) * 256, (tile_y - tile_y_min) * 256))
                loaded_tiles += 1
            except Exception:
                continue

    if loaded_tiles == 0:
        return None

    crop_left = int(round(x_left - tile_x_min * 256.0))
    crop_top = int(round(y_top - tile_y_min * 256.0))
    crop_right = int(round(x_right - tile_x_min * 256.0))
    crop_bottom = int(round(y_bottom - tile_y_min * 256.0))
    crop_right = max(crop_right, crop_left + 1)
    crop_bottom = max(crop_bottom, crop_top + 1)
    return mosaic.crop((crop_left, crop_top, crop_right, crop_bottom))


def _report_map_bytes(df_plot: pd.DataFrame, title: str) -> bytes | None:
    """
    Erzeugt das fertige Kartenbild für den PDF-Bericht.
    
    Inputs: df_plot, title.
    Outputs: PNG-Bild als bytes.
    """
    if df_plot is None or df_plot.empty:
        return None

    width = 1280
    height = 1180
    icon_cache = {}
    try:
        from PIL import Image
    except Exception:
        Image = None

    def _draw(_img, draw):
        def _get_icon(layer_key: str):
            if Image is None:
                return None
            key = str(layer_key)
            if key in icon_cache:
                return icon_cache[key]
            filename = MAP_LAYER_ICON_FILES.get(key, "")
            if not filename:
                icon_cache[key] = None
                return None
            icon_path = os.path.join(BASE_DIR, "assets", MAP_ICON_ASSET_DIR, filename)
            if not os.path.isfile(icon_path):
                icon_cache[key] = None
                return None
            try:
                icon_cache[key] = Image.open(icon_path).convert("RGBA")
            except Exception:
                icon_cache[key] = None
            return icon_cache[key]

        def _draw_map_legend(entries: list[dict], x: int, y: int, width: int) -> int:
            font = _report_pil_font(16, bold=False)
            cursor_x = x
            cursor_y = y
            line_h = 58
            for entry in entries:
                text = f"{entry['layer_label']} ({int(entry['count'])})"
                icon = _get_icon(str(entry["layer_key"]))
                tw, _ = _report_pil_text_size(draw, text, font)
                block_w = 58 + 12 + tw + 20
                if cursor_x + block_w > x + width:
                    cursor_x = x
                    cursor_y += line_h + 6
                if icon is not None and Image is not None:
                    icon_thumb = icon.copy()
                    icon_thumb.thumbnail((52, 52), Image.LANCZOS)
                    _img.paste(icon_thumb, (int(cursor_x), int(cursor_y)), icon_thumb)
                else:
                    color = _report_normalize_color(entry.get("marker_color"), "#64748b") or "#64748b"
                    draw.rectangle((cursor_x, cursor_y + 10, cursor_x + 34, cursor_y + 34), fill=color, outline=color)
                _, th = _report_pil_text_size(draw, text, font)
                text_y = cursor_y + max(0, int((52 - th) / 2))
                draw.text((cursor_x + 60, text_y), text, fill="#334155", font=font)
                cursor_x += block_w
            return cursor_y + line_h + 8

        title_y = _report_pil_draw_title(draw, title, 36, 24, width - 72)

        legend_df = (
            df_plot.groupby(["map_layer_key", "layer_label", "marker_color"], dropna=False)
            .size()
            .reset_index(name="count")
        )
        legend_entries = [
            {
                "layer_key": str(row["map_layer_key"]),
                "layer_label": str(row["layer_label"]),
                "marker_color": row["marker_color"],
                "count": int(row["count"]),
            }
            for _, row in legend_df.iterrows()
        ]
        legend_y = _draw_map_legend(legend_entries, 36, title_y, width - 72)

        left = 100
        right = width - 55
        top = legend_y + 18
        bottom = height - 90
        chart_w = right - left
        chart_h = bottom - top
        map_side = min(chart_w, chart_h)
        left = left + (chart_w - map_side) / 2
        right = left + map_side
        top = top + (chart_h - map_side) / 2
        bottom = top + map_side
        chart_w = map_side
        chart_h = map_side

        lon_min = float(df_plot["lon"].min())
        lon_max = float(df_plot["lon"].max())
        lat_min = float(df_plot["lat"].min())
        lat_max = float(df_plot["lat"].max())
        lon_span = max(lon_max - lon_min, 1e-6)
        lat_span = max(lat_max - lat_min, 1e-6)
        lon_pad = max(0.002, lon_span * 0.1)
        lat_pad = max(0.002, lat_span * 0.1)
        lon_min -= lon_pad
        lon_max += lon_pad
        lat_min -= lat_pad
        lat_max += lat_pad

        basemap_img = None
        basemap_zoom = int(round(_map_zoom_from_extent(df_plot))) + 2
        basemap_zoom = max(8, min(19, basemap_zoom))
        while basemap_zoom >= 8 and basemap_img is None:
            basemap_img = _report_osm_basemap_image(lon_min, lon_max, lat_min, lat_max, basemap_zoom)
            if basemap_img is None:
                basemap_zoom -= 1

        font = _report_pil_font(12)
        small_font = _report_pil_font(11)
        symbol_font = _report_pil_font(10, bold=True)

        if basemap_img is not None and Image is not None:
            map_bg = basemap_img.resize((int(chart_w), int(chart_h)), Image.LANCZOS)
            _img.paste(map_bg, (int(left), int(top)))
            overlay = Image.new("RGBA", (int(chart_w), int(chart_h)), (255, 255, 255, 10))
            _img.paste(overlay, (int(left), int(top)), overlay)
            draw.rectangle((left, top, right, bottom), outline="#94a3b8", width=2)
        else:
            draw.rectangle((left, top, right, bottom), outline="#94a3b8", width=2)
            for tick in range(5):
                x = left + tick * chart_w / 4
                y = top + tick * chart_h / 4
                draw.line((x, top, x, bottom), fill="#e2e8f0", width=1)
                draw.line((left, y, right, y), fill="#e2e8f0", width=1)

                lon_val = lon_min + tick * (lon_max - lon_min) / 4
                lon_text = _report_format_number(lon_val, 4)
                tw, _ = _report_pil_text_size(draw, lon_text, small_font)
                draw.text((x - tw / 2, bottom + 8), lon_text, fill="#64748b", font=small_font)

                lat_val = lat_max - tick * (lat_max - lat_min) / 4
                lat_text = _report_format_number(lat_val, 4)
                tw, th = _report_pil_text_size(draw, lat_text, small_font)
                draw.text((left - tw - 10, y - th / 2), lat_text, fill="#64748b", font=small_font)

            draw.text((left, top - 24), f"Latitude [{MAP_CRS_NAME}]", fill="#475569", font=font)
            x_label = f"Longitude [{MAP_CRS_NAME}]"
            tw, _ = _report_pil_text_size(draw, x_label, font)
            draw.text((left + chart_w / 2 - tw / 2, height - 42), x_label, fill="#475569", font=font)

        ordered = df_plot.copy()
        ordered["_layer_order"] = ordered.apply(
            lambda row: _map_layer_order_value(str(row.get("map_layer_key", "")), str(row.get("component", ""))),
            axis=1,
        ).astype(int)
        ordered = ordered.sort_values(["_layer_order", "display_name"]).drop(columns=["_layer_order"])

        for _, row in ordered.iterrows():
            lon = float(row["lon"])
            lat = float(row["lat"])
            x = left + (lon - lon_min) / (lon_max - lon_min) * chart_w
            y = bottom - (lat - lat_min) / (lat_max - lat_min) * chart_h
            marker_size = float(row.get("marker_size", 12) or 12)
            component_count = int(row.get("component_count", 1) or 1)
            radius = int(max(26, min(46, marker_size * 2.1 + min(component_count - 1, 3) * 3)))
            fill = _report_normalize_color(row.get("marker_color"), "#0f3554") or "#0f3554"
            layer_key = str(row.get("map_layer_key", "") or "")
            icon_image = _get_icon(layer_key)
            if icon_image is not None:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#ffffff", outline=fill, width=2)
                icon_size = int(max(52, min(88, radius * 2.0)))
                icon = icon_image.copy()
                icon.thumbnail((icon_size, icon_size), Image.LANCZOS)
                ix = int(round(x - icon.width / 2))
                iy = int(round(y - icon.height / 2))
                _img.paste(icon, (ix, iy), icon)
            else:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline="#ffffff", width=2)
                symbol = str(row.get("marker_symbol", "") or "").strip()
                symbol = symbol[:4] if symbol else ""
                if symbol:
                    tw, th = _report_pil_text_size(draw, symbol, symbol_font)
                    draw.text((x - tw / 2, y - th / 2), symbol, fill="white", font=symbol_font)

            if component_count > 1:
                badge_r = 15
                badge_x = x + radius - 2
                badge_y = y - radius + 2
                draw.ellipse((badge_x - badge_r, badge_y - badge_r, badge_x + badge_r, badge_y + badge_r), fill="#ffffff", outline="#334155", width=1)
                badge_text = str(component_count)
                btw, bth = _report_pil_text_size(draw, badge_text, small_font)
                draw.text((badge_x - btw / 2, badge_y - bth / 2 - 1), badge_text, fill="#0f172a", font=small_font)

        note = (
            f"{OSM_ATTRIBUTION_TEXT}; interaktive Dashboard-Einbindung: Leaflet."
            if basemap_img is not None
            else "Schematische Lage der verorteten Komponenten auf Basis der im PyPSA-Netzwerk hinterlegten Koordinaten (EPSG:4326)."
        )
        draw.text((left, height - 18), note, fill="#64748b", font=small_font)

    return _report_pil_bytes(width, height, _draw, title)


def _report_export_scope_selections(
    st: dict,
    export_period_mode,
    export_period_values,
    export_sector_mode,
    export_sector_values,
    map_components=None,
) -> dict:
    """
    Validiert und bündelt alle wichtigen Auswahlwerte für den PDF-Export.
    
    Inputs: st, export_period_mode, export_period_values, export_sector_mode, export_sector_values, map_components.
    Outputs: Dictionary mit bereinigten Export-Einstellungen für den PDF-Bericht.
    """
    export_periods = _report_validate_export_periods(st, export_period_mode, export_period_values)
    export_sectors = _report_validate_export_sectors(st, export_sector_mode, export_sector_values)
    primary_period = export_periods[0] if export_periods else "Single"
    primary_sector = export_sectors[0] if export_sectors else st.get("default_sector", SECTORS[-1])
    return {
        "export_periods": export_periods,
        "export_sectors": export_sectors,
        "cap_sector": primary_sector,
        "cap_period": primary_period if len(export_periods) == 1 else "all",
        "exp_sector": primary_sector,
        "ops_period": primary_period,
        "sankey_period": primary_period,
        "co2_period": primary_period,
        "cost_compare_period": primary_period,
        "map_period": primary_period if len(export_periods) == 1 else "all",
        "map_components": _report_validate_map_components(st, map_components),
    }


def _build_pdf_report_bytes_scientific_v2(nc_path: str, st: dict, selections: dict) -> tuple[bytes, list[str]]:
    """
    Erzeugt den kompletten PDF-Bericht aus den Dashboard-Daten mit den jeweiligen Unterfunktionen.
    
    Inputs: nc_path, st, selections.
    Outputs: Fertiger PDF-Bericht.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image as RLImage,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.pdfgen import canvas as pdf_canvas
    except ImportError as exc:
        raise RuntimeError(
            "Für den PDF-Export wird das Python-Paket 'reportlab' benötigt."
        ) from exc

    warnings: list[str] = []
    selected_periods = [str(v) for v in (selections.get("export_periods") or _report_available_periods(st))]
    selected_sectors = [str(v) for v in (selections.get("export_sectors") or _report_available_export_sectors(st))]
    dataset_name = _basename(nc_path)
    analysis_mode = "Mehrperioden-Analyse" if st.get("has_mip", False) else "Einjahresanalyse"
    created_at = datetime.now().strftime("%d.%m.%Y %H:%M")
    export_sector_label = ", ".join(selected_sectors) if selected_sectors else "-"

    n = st.get("n")
    df_cost_scope = _report_attach_sector_columns(n, st.get("df_total_cost", pd.DataFrame()))
    if not df_cost_scope.empty:
        df_cost_scope = _report_filter_periods(df_cost_scope, selected_periods)
        df_cost_scope = df_cost_scope[df_cost_scope["sector"].astype(str).isin(selected_sectors)].copy()

    df_inv_scope = _report_attach_sector_columns(n, st.get("df_inv_capex", pd.DataFrame()))
    if not df_inv_scope.empty:
        df_inv_scope = _report_filter_periods(df_inv_scope, selected_periods)
        df_inv_scope = df_inv_scope[df_inv_scope["sector"].astype(str).isin(selected_sectors)].copy()

    df_sector_lcoe = _report_filter_periods(st.get("df_sector_lcoe", pd.DataFrame()), selected_periods)
    df_lcos_scope = _report_filter_periods(st.get("df_lcos", pd.DataFrame()), selected_periods)
    if not df_lcos_scope.empty and "sector" in df_lcos_scope.columns:
        df_lcos_scope = df_lcos_scope[df_lcos_scope["sector"].astype(str).isin(selected_sectors)].copy()
    df_emissions_scope = _report_filter_periods(st.get("df_emissions", pd.DataFrame()), selected_periods)
    if not df_emissions_scope.empty and "sector" in df_emissions_scope.columns:
        df_emissions_scope = df_emissions_scope[df_emissions_scope["sector"].astype(str).isin(selected_sectors)].copy()
    df_ops_scope = _report_filter_periods(st.get("df_ops_autarky", pd.DataFrame()), selected_periods)
    df_load_metrics_scope = _report_filter_periods(st.get("df_ops_load_metrics", pd.DataFrame()), selected_periods)

    def _capacity_detail_df(value_col: str) -> pd.DataFrame:
        by_key = "by_sector_p" if value_col == "p_nom" else "by_sector_e"
        frames = []
        for sector in selected_sectors:
            df_sector = st.get(by_key, {}).get(sector, pd.DataFrame())
            if df_sector is None or df_sector.empty or value_col not in df_sector.columns:
                continue
            d = df_sector.copy()
            if "year" in d.columns:
                d["period"] = d["year"].astype(str)
            elif "period" in d.columns:
                d["period"] = d["period"].astype(str)
            else:
                d["period"] = "Single"
            d["sector"] = sector
            if "subcarrier" in d.columns:
                d["subcarrier"] = d["subcarrier"].fillna(DEFAULT_SUBCARRIER).astype(str)
            else:
                d["subcarrier"] = DEFAULT_SUBCARRIER
            d = _report_filter_periods(d, selected_periods, col="period")
            if d.empty:
                continue
            frames.append(d)
        if not frames:
            return pd.DataFrame(columns=["period", "sector", "subcarrier", "component", "label", "base_name", value_col])
        return pd.concat(frames, ignore_index=True)

    def _aggregate_capacity_detail(df_detail: pd.DataFrame, value_col: str) -> pd.DataFrame:
        if df_detail is None or df_detail.empty or value_col not in df_detail.columns:
            return pd.DataFrame(columns=["period", "sector", "subcarrier", value_col])
        d = df_detail.copy()
        d[value_col] = pd.to_numeric(d[value_col], errors="coerce").fillna(0.0)
        return (
            d.groupby(["period", "sector", "subcarrier"], dropna=False)[value_col]
            .sum()
            .reset_index()
        )

    def _is_excluded_power_row(row: pd.Series) -> bool:
        text_parts = [
            str(row.get("label", "") or ""),
            str(row.get("base_name", "") or ""),
            str(row.get("subcarrier", "") or ""),
            str(row.get("component", "") or ""),
        ]
        text = " ".join(text_parts)
        if str(row.get("component", "") or "") == "storage_units":
            return True
        exclusion_patterns = [
            r"einspeis",
            r"netzbezug",
            r"netzanschlusspunkt",
            r"gasnetz",
            r"speicher",
            r"stromnutzung",
            r"exportleitung",
            r"_laden",
            r"_entladen",
        ]
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in exclusion_patterns)

    def _report_power_technology_group(row: pd.Series) -> str | None:
        sector_value = str(row.get("sector", "") or "").strip()
        text = " ".join([
            str(row.get("label", "") or ""),
            str(row.get("base_name", "") or ""),
            str(row.get("subcarrier", "") or ""),
            str(row.get("component", "") or ""),
            sector_value,
        ])
        if re.search(r"einspeis|netz|speicher|stromlast|wärmelast|waermelast|gasnetz|stromnutzung|exportleitung|_laden|_entladen", text, flags=re.IGNORECASE):
            return None
        if re.search(r"fernw(?:ä|ae)rme", text, flags=re.IGNORECASE):
            return "Fernwärmebezug" if sector_value == "Wärme" else None
        if re.search(r"solarthermie", text, flags=re.IGNORECASE):
            return "Solarthermie" if sector_value == "Wärme" else None
        if re.search(r"wärmepumpe|waermepumpe", text, flags=re.IGNORECASE):
            return "Wärmepumpe" if sector_value == "Wärme" else None
        if re.search(r"gaskessel", text, flags=re.IGNORECASE):
            return "Gaskessel" if sector_value == "Wärme" else None
        if re.search(r"bhkw", text, flags=re.IGNORECASE):
            return "BHKW"
        if re.search(r"(^|[^a-z])pv([^a-z]|$)", text, flags=re.IGNORECASE):
            return "PV" if sector_value == "Strom" else None
        return _report_pretty_label(str(row.get("subcarrier", "") or row.get("label", "") or "")).strip() or None

    def _report_power_component_priority(technology: str) -> list[str]:
        if technology in {"PV", "Solarthermie", "Fernwärmebezug"}:
            return ["generators", "links", "storage_units"]
        return ["links", "generators", "storage_units"]

    def _build_power_scope_for_report(df_detail: pd.DataFrame) -> pd.DataFrame:
        if df_detail is None or df_detail.empty or "p_nom" not in df_detail.columns:
            return pd.DataFrame(columns=["period", "sector", "subcarrier", "p_nom"])

        d = df_detail.copy()
        if "component" in d.columns and "port" in d.columns:
            d = d[~((d["component"].astype(str) == "links") & (~d["port"].astype(str).str.startswith("out")))].copy()
        d["technology"] = d.apply(_report_power_technology_group, axis=1)
        d = d[d["technology"].notna()].copy()
        d["technology"] = d["technology"].astype(str).str.strip()
        d["p_nom"] = pd.to_numeric(d["p_nom"], errors="coerce").fillna(0.0)
        d = d[d["p_nom"] > 1e-9].copy()
        if d.empty:
            return pd.DataFrame(columns=["period", "sector", "subcarrier", "p_nom"])

        rows = []
        for (period, sector, technology), group in d.groupby(["period", "sector", "technology"], dropna=False):
            chosen = group
            for component_name in _report_power_component_priority(str(technology)):
                group_component = group[group["component"].astype(str) == str(component_name)]
                if not group_component.empty:
                    chosen = group_component
                    break
            value = float(chosen["p_nom"].sum())
            if value <= 1e-9:
                continue
            rows.append({
                "period": str(period),
                "sector": str(sector),
                "subcarrier": str(technology),
                "p_nom": value,
            })

        if not rows:
            return pd.DataFrame(columns=["period", "sector", "subcarrier", "p_nom"])
        return pd.DataFrame(rows)

    df_power_detail = _capacity_detail_df("p_nom")
    df_power_detail_local = df_power_detail[~df_power_detail.apply(_is_excluded_power_row, axis=1)].copy() if not df_power_detail.empty else df_power_detail
    df_power_scope = _build_power_scope_for_report(df_power_detail_local)
    df_energy_detail = _capacity_detail_df("e_nom")
    df_energy_scope = _aggregate_capacity_detail(df_energy_detail, "e_nom")
    df_map = _report_map_collapse_period_variants(_report_map_filtered_df(st, selections))
    df_map_plot = prepare_map_components_for_plot(df_map, aggregate_overlapping_points=True) if not df_map.empty else pd.DataFrame()
    # Summiert einen numerischen Kennwert für eine ausgewählte Berichtsperiode.
    def _period_sum(df: pd.DataFrame, period: str, value_col: str) -> float | None:
        d = _report_filter_period(df, period)
        if d.empty or value_col not in d.columns:
            return None
        values = pd.to_numeric(d[value_col], errors="coerce").fillna(0.0)
        return float(values.sum())
    # Summiert installierte Leistungen für den PDF-Bericht, optional nach Sektor.
    def _power_scope_sum(period: str, sector: str | None = None) -> float | None:
        d = _report_filter_period(df_power_scope, period)
        if d.empty or "p_nom" not in d.columns:
            return None
        if sector is not None and "sector" in d.columns:
            d = d[d["sector"].astype(str) == str(sector)]
        if d.empty:
            return None
        values = pd.to_numeric(d["p_nom"], errors="coerce").fillna(0.0)
        return float(values.sum())
    # Ermittelt den mittleren Wert der spezifischen Gestehungskosten eines Sektors.
    def _sector_lcoe_value(period: str, sector: str):
        d = _report_filter_period(df_sector_lcoe, period)
        if d.empty or "sector" not in d.columns:
            return None
        d = d[d["sector"].astype(str) == str(sector)]
        if d.empty:
            return None
        row = d.iloc[0]
        value_per_kwh = _report_safe_float(row.get("lcoe_eur_per_kwh"))
        if value_per_kwh is not None:
            return value_per_kwh * 100.0
        value_per_mwh = _report_safe_float(row.get("lcoe_eur_per_mwh"))
        if value_per_mwh is not None:
            return value_per_mwh / 10.0
        return None
    # Berechnet oder formatiert spezifische Gestehungskosten für spezifische Speicherkosten value.
    def _lcos_value(period: str):

        d = _report_filter_period(df_lcos_scope, period)
        if d.empty or "energy_kwh" not in d.columns or "total_cost" not in d.columns:
            return None
        energy_total = float(pd.to_numeric(d["energy_kwh"], errors="coerce").fillna(0.0).sum())
        cost_total = float(pd.to_numeric(d["total_cost"], errors="coerce").fillna(0.0).sum())
        if energy_total <= 1e-9:
            return None
        return cost_total / energy_total * 100.0

    def _storage_capacity_value(period: str, sector: str):
        d = _report_filter_period(df_energy_scope, period)
        if d.empty or "sector" not in d.columns or "e_nom" not in d.columns:
            return None
        d = d[d["sector"].astype(str) == str(sector)]
        if d.empty:
            return None
        value = float(pd.to_numeric(d["e_nom"], errors="coerce").fillna(0.0).sum())
        return value if abs(value) > 1e-9 else None

    def _load_metric(period: str, series_name: str, value_col: str = "peak_kw"):
        d = _report_filter_period(df_load_metrics_scope, period)
        if d.empty or "series" not in d.columns or value_col not in d.columns:
            return None
        d = d[d["series"].astype(str) == str(series_name)]
        if d.empty:
            return None
        return _report_safe_float(d.iloc[0].get(value_col))

    def _top_emitter_text(period: str) -> str | None:
        d = _report_filter_period(df_emissions_scope, period)
        if d.empty or "base_name" not in d.columns or "emissions_t" not in d.columns:
            return None
        grouped = (
            d.groupby("base_name")["emissions_t"]
            .sum()
            .sort_values(ascending=False)
        )
        grouped = grouped[grouped.abs() > 1e-9]
        if grouped.empty:
            return None
        return f"{_report_pretty_label(grouped.index[0])} ({_report_format_emissions(float(grouped.iloc[0]))})"

    def _co2_price_for_period(period: str) -> float | None:
        """
        Ermittelt den im PDF auszuweisenden CO2-Preis je Periode. Bei mehreren Preisen wird
        emissionsgewichtet gemittelt; ohne Emissionsmenge wird der Mittelwert der vorhandenen
        positiven Preise verwendet.
        """
        d = _report_filter_period(df_emissions_scope, period)
        if d.empty or "co2_price_eur_per_t" not in d.columns:
            return None
        prices = pd.to_numeric(d["co2_price_eur_per_t"], errors="coerce").fillna(0.0)
        if "emissions_t" in d.columns:
            emissions = pd.to_numeric(d["emissions_t"], errors="coerce").fillna(0.0)
        else:
            emissions = pd.Series(0.0, index=d.index)
        weighted_mask = (prices > 0.0) & (emissions.abs() > 1e-9)
        if bool(weighted_mask.any()):
            weight_sum = float(emissions[weighted_mask].abs().sum())
            if weight_sum > 1e-9:
                return float((prices[weighted_mask] * emissions[weighted_mask].abs()).sum() / weight_sum)
        positive_prices = prices[prices > 0.0]
        if positive_prices.empty:
            return None
        return float(positive_prices.mean())

    def _row_has_values(values) -> bool:
        for value in values:
            if value not in (None, "-", ""):
                return True
        return False

    show_electric_storage = any((_storage_capacity_value(period, "Strom") or 0.0) > 1e-9 for period in selected_periods)
    show_heat_storage = any((_storage_capacity_value(period, "Wärme") or 0.0) > 1e-9 for period in selected_periods)

    overview_rows = []
    for period in selected_periods:
        power_total = _power_scope_sum(period)
        total_cost = _period_sum(df_cost_scope, period, "total_cost")
        total_investment = _period_sum(df_inv_scope, period, "investment_capex")
        total_emissions = _period_sum(df_emissions_scope, period, "emissions_t")
        ops_row = _report_first_period_row(df_ops_scope, period)

        row_values = [
            str(period),
            _report_format_power(power_total),
        ]
        if show_electric_storage:
            row_values.append(_report_format_energy(_storage_capacity_value(period, "Strom")))
        if show_heat_storage:
            row_values.append(_report_format_energy(_storage_capacity_value(period, "Wärme")))
        row_values.extend([
            _report_format_currency_per_year(total_cost),
            _report_format_currency_once(total_investment),
            _report_format_emissions(total_emissions),
            _report_format_percent(ops_row.get("electric_autarky_pct") if ops_row is not None else None, 1),
        ])
        overview_rows.append(tuple(row_values))

    capacity_rows = []
    for period in selected_periods:
        for sector in selected_sectors:
            d_power = _report_filter_period(df_power_scope, period)
            if not d_power.empty and "sector" in d_power.columns:
                d_power = d_power[d_power["sector"].astype(str) == str(sector)].copy()

            power_total = float(pd.to_numeric(d_power.get("p_nom", 0.0), errors="coerce").fillna(0.0).sum()) if not d_power.empty else 0.0
            electric_storage = _storage_capacity_value(period, "Strom") if str(sector) == "Strom" else None
            heat_storage = _storage_capacity_value(period, "Wärme") if str(sector) == "Wärme" else None
            if abs(power_total) <= 1e-9 and (electric_storage in (None, 0.0)) and (heat_storage in (None, 0.0)):
                continue

            dominant = "-"
            if not d_power.empty:
                dominant_series = (
                    d_power.groupby("subcarrier")["p_nom"]
                    .sum()
                    .sort_values(ascending=False)
                )
                dominant_series = dominant_series[dominant_series > 1e-9]
                if not dominant_series.empty:
                    dominant = ", ".join(str(idx) for idx in dominant_series.index[:3])

            row_values = [
                str(period),
                str(sector),
                _report_format_power(power_total),
            ]
            if show_electric_storage:
                row_values.append(_report_format_energy(electric_storage) if str(sector) == "Strom" else "-")
            if show_heat_storage:
                row_values.append(_report_format_energy(heat_storage) if str(sector) == "Wärme" else "-")
            row_values.append(dominant)
            capacity_rows.append(tuple(row_values))

    ops_summary_rows = []
    ops_peak_rows = []
    ops_specific_cost_rows = []
    for period in selected_periods:
        ops_row = _report_first_period_row(df_ops_scope, period)
        lcoe_strom = _sector_lcoe_value(period, "Strom") if "Strom" in selected_sectors else None
        lcoh_waerme = _sector_lcoe_value(period, "Wärme") if "Wärme" in selected_sectors else None
        lcos_storage = _lcos_value(period)

        summary_row = (
            str(period),
            _report_format_percent(ops_row.get("electric_autarky_pct") if ops_row is not None else None, 1),
            _report_format_percent(ops_row.get("heat_autarky_pct") if ops_row is not None else None, 1),
            _report_format_percent(ops_row.get("pv_self_consumption_pct") if ops_row is not None else None, 1),
            _report_format_percent(ops_row.get("pv_feed_in_pct") if ops_row is not None else None, 1),
        )
        if _row_has_values(summary_row[1:]):
            ops_summary_rows.append(summary_row)

        peak_row = (
            str(period),
            _report_format_power(_load_metric(period, "Gesamtstromlast")),
            _report_format_power(_load_metric(period, "Reststromlast nach Erzeugung")),
            _report_format_power(_load_metric(period, "Wärmelast")),
        )
        if _row_has_values(peak_row[1:]):
            ops_peak_rows.append(peak_row)

        specific_cost_row = (
            str(period),
            _report_format_lcoe(lcoe_strom),
            _report_format_lcoe(lcoh_waerme),
            _report_format_lcoe(lcos_storage),
        )
        if _row_has_values(specific_cost_row[1:]):
            ops_specific_cost_rows.append(specific_cost_row)

    cost_rows = []
    for period in selected_periods:
        d_cost_period = _report_filter_period(df_cost_scope, period)
        d_cost_work = _with_opex_including_co2(d_cost_period) if not d_cost_period.empty else pd.DataFrame()
        total_cost = _period_sum(df_cost_scope, period, "total_cost")
        annual_capex = _period_sum(d_cost_work, period, "capex") if not d_cost_work.empty else None
        annual_opex = _period_sum(d_cost_work, period, "opex_incl_co2") if not d_cost_work.empty else None
        co2_cost = _period_sum(df_cost_scope, period, "co2_cost")
        total_investment = _period_sum(df_inv_scope, period, "investment_capex")
        row = (
            str(period),
            _report_format_currency_per_year(total_cost),
            _report_format_currency_per_year(annual_capex),
            _report_format_currency_per_year(annual_opex),
            _report_format_currency_per_year(co2_cost),
            _report_format_currency_once(total_investment),
        )
        if _row_has_values(row[1:]):
            cost_rows.append(row)

    emission_rows = []
    for period in selected_periods:
        total_emissions = _period_sum(df_emissions_scope, period, "emissions_t")
        co2_cost = _period_sum(df_emissions_scope, period, "co2_cost_eur")
        co2_price = _co2_price_for_period(period)
        top_emitter = _top_emitter_text(period)
        row = (
            str(period),
            _report_format_emissions(total_emissions),
            _report_format_co2_price(co2_price),
            _report_format_currency_per_year(co2_cost),
            top_emitter or "-",
        )
        if _row_has_values(row[1:]):
            emission_rows.append(row)

    map_overview_rows = _report_map_overview_rows(df_map, df_map_plot, selected_periods)

    map_fig = _report_map_bytes(df_map_plot, "Systemkarte") if not df_map_plot.empty else None
    capacity_power_fig = _report_mpl_capacity_scope_bytes(
        df_power_scope,
        title="Nennleistungen nach Periode und Sektor",
        value_col="p_nom",
        unit="kW",
        period_order=selected_periods,
        sector_order=selected_sectors,
        color_map=st.get("subcarrier_color_map"),
    )
    capacity_energy_fig = _report_mpl_capacity_scope_bytes(
        df_energy_scope,
        title="Speicherkapazitäten nach Periode und Sektor",
        value_col="e_nom",
        unit="kWh",
        period_order=selected_periods,
        sector_order=selected_sectors,
        color_map=st.get("subcarrier_color_map"),
    )
    has_map_section = not df_map_plot.empty
    has_capacity_section = bool(capacity_rows)
    has_ops_section = bool(ops_summary_rows or ops_peak_rows or ops_specific_cost_rows)
    has_cost_section = bool(cost_rows)
    has_emission_section = bool(emission_rows)

    if not has_map_section:
        warnings.append("Abschnitt 'Systembeschreibung und räumliche Einordnung' wurde ausgelassen, da im gewählten Exportumfang keine georeferenzierten Komponenten vorliegen.")
    if not has_capacity_section:
        warnings.append("Abschnitt 'Dimensionierung und Ausbau' wurde ausgelassen, da für die gewählten Perioden und Sektoren keine Kapazitätsdaten vorliegen.")
    if not has_ops_section:
        warnings.append("Abschnitt 'Betriebliche Ergebnisse' wurde ausgelassen, da im gewählten Exportumfang keine auswertbaren Betriebskennzahlen vorliegen.")
    if not has_cost_section:
        warnings.append("Abschnitt 'Wirtschaftliche Ergebnisse' wurde ausgelassen, da im gewählten Exportumfang keine auswertbaren Kostendaten vorliegen.")
    if not has_emission_section:
        warnings.append("Abschnitt 'Emissionsbezogene Ergebnisse' wurde ausgelassen, da im gewählten Exportumfang keine Emissionsdaten vorliegen.")

    section_candidates = [
        ("overview", "Kurzübersicht", True, "Zentrale Kennzahlen für alle ausgewählten Perioden"),
        ("system", "Systembeschreibung und räumliche Einordnung", has_map_section, "Räumliche Einordnung und Kartenübersicht"),
        ("capacity", "Dimensionierung und Ausbau", has_capacity_section, "Installierte Leistungen und Speicherkapazitäten"),
        ("ops", "Betriebliche Ergebnisse", has_ops_section, "Autarkie, Lastspitzen und sektorale Kennzahlen"),
        ("cost", "Wirtschaftliche Ergebnisse", has_cost_section, "Kosten- und Investitionskennzahlen"),
        ("co2", "Emissionsbezogene Ergebnisse", has_emission_section, "Emissionen und CO2-bezogene Kosten"),
        ("methods", "Methodische Hinweise", True, "Abgrenzung, Interpretation und Exporthinweise"),
    ]
    section_numbers = {}
    section_counter = 1
    toc_rows = []
    for key, title, enabled, description in section_candidates:
        if not enabled:
            continue
        section_numbers[key] = section_counter
        toc_rows.append((f"{section_counter}. {title}", description))
        section_counter += 1

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=REPORT_MARGIN_LEFT_MM * mm,
        rightMargin=REPORT_MARGIN_RIGHT_MM * mm,
        topMargin=REPORT_MARGIN_TOP_MM * mm,
        bottomMargin=REPORT_MARGIN_BOTTOM_MM * mm,
        title=f"Energiebericht - {dataset_name}",
        author="PyPSA Dashboard",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitleScientificV2",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#0f3554"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitleScientificV2",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#536471"),
        spaceAfter=12,
    )
    h1_style = ParagraphStyle(
        "ReportH1ScientificV2",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#0f3554"),
        spaceAfter=8,
    )
    h2_style = ParagraphStyle(
        "ReportH2ScientificV2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0f3554"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "ReportBodyScientificV2",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        alignment=TA_LEFT,
        spaceAfter=7,
    )
    small_style = ParagraphStyle(
        "ReportSmallScientificV2",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#536471"),
        spaceAfter=5,
    )
    table_body_style = ParagraphStyle(
        "ReportTableBodyScientificV2",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.7,
        leading=10,
        alignment=TA_LEFT,
    )
    table_header_style = ParagraphStyle(
        "ReportTableHeaderScientificV2",
        parent=table_body_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f3554"),
    )

    def _paragraph(value, style):
        """
        Wandelt Textwerte in ReportLab-Paragraphen um und escaped dabei HTML-Zeichen.
        
        Inputs: value, style.
        Outputs: formatierter ReportLab-Paragraph.
        """
        return Paragraph(html_escape(str(value)).replace("\n", "<br/>"), style)

    def _make_rl_image(image_bytes: bytes | bytearray | None, max_height_mm: float) -> RLImage | None:
        """
        Erstellt aus Bildbytes ein skalierbares ReportLab-Bildelement.
        
        Inputs: image_bytes, max_height_mm.
        Outputs: ReportLab-Image oder None bei fehlenden Bilddaten.
        """
        if image_bytes is None:
            return None
        img = RLImage(io.BytesIO(image_bytes))
        max_width = doc.width
        max_height = max_height_mm * mm
        scale = min(max_width / float(img.imageWidth), max_height / float(img.imageHeight))
        img.drawWidth = float(img.imageWidth) * scale
        img.drawHeight = float(img.imageHeight) * scale
        return img

    def _matrix_table(headers: list[str], rows: list[tuple], col_widths: list[float]) -> Table | None:
        """
        Baut eine formatierte ReportLab-Tabelle mit Kopfzeile und Datenzeilen.
        
        Inputs: headers, rows, col_widths.
        Outputs: ReportLab-Tabelle oder None bei fehlenden Zeilen.
        """
        if not rows:
            return None
        data = [[_paragraph(h, table_header_style) for h in headers]]
        for row in rows:
            data.append([_paragraph(value, table_body_style) for value in row])
        table = Table(data, colWidths=[doc.width * w for w in col_widths], hAlign="LEFT", repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4f8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f3554")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d8dee6")),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8dee6")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    def _kv_table(rows: list[tuple[str, str]], key_ratio: float = 0.38) -> Table | None:
        """
        Baut eine zweispaltige ReportLab-Tabelle für Kennzahl-Wert-Paare.
        
        Inputs: rows, key_ratio.
        Outputs: ReportLab-Tabelle oder None bei fehlenden Zeilen.
        """
        if not rows:
            return None
        table = Table(
            [[_paragraph(label, table_body_style), _paragraph(value, table_body_style)] for label, value in rows],
            colWidths=[doc.width * key_ratio, doc.width * (1.0 - key_ratio)],
            hAlign="LEFT",
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f8fb")),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d8dee6")),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8dee6")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#0f3554")),
        ]))
        return table

    def _append_optional_figure(
        story: list,
        title: str,
        image_bytes: bytes | bytearray | None,
        label: str,
        caption: str,
        max_height_mm: float,
        has_content: bool,
        missing_reason: str,
    ) -> None:
        """
        Fügt ein Diagramm nur dann in den PDF-Bericht ein, wenn verwertbare Bilddaten vorliegen.
        
        Inputs: story, title, image_bytes, label, caption, max_height_mm, has_content, missing_reason.
        Outputs: Inplace-Anpassung oder keine Rückgabe.
        """
        if not has_content:
            warnings.append(f"Diagramm '{label}' wurde nicht aufgenommen: {missing_reason}")
            return
        img = _make_rl_image(image_bytes, max_height_mm)
        if img is None:
            warnings.append(f"Diagramm '{label}' konnte nicht in das PDF eingebettet werden.")
            return
        story.append(Paragraph(title, h2_style))
        story.append(img)
        if str(caption).strip():
            story.append(Spacer(1, 4))
            story.append(Paragraph(html_escape(caption), small_style))
        story.append(Spacer(1, 6))

    story = []
    story.append(Paragraph("Energiebericht", title_style))
    story.append(Paragraph(
        "Automatisch erzeugter Bericht auf Basis der serverseitigen Dashboard-Berechnungen. "
        "Der Export verdichtet technische, wirtschaftliche und emissionsbezogene Kennzahlen für den gewählten Berichtsumfang.",
        subtitle_style,
    ))
    story.append(Paragraph(
        f"<b>{html_escape(dataset_name)}</b><br/>"
        f"{html_escape(analysis_mode)}<br/>"
        f"Exportumfang Perioden: {html_escape(_report_scope_label(selected_periods))}<br/>"
        f"Exportumfang Sektoren: {html_escape(export_sector_label)}<br/>"
        f"Erstellt am {html_escape(created_at)}",
        body_style,
    ))
    story.append(Spacer(1, 6))

    story.append(Paragraph(f"{section_numbers['overview']}. Kurzübersicht", h1_style))
    overview_headers = ["Periode", "Installierte Leistung"]
    if show_electric_storage and show_heat_storage:
        overview_widths = [0.10, 0.12]
    elif show_electric_storage or show_heat_storage:
        overview_widths = [0.11, 0.14]
    else:
        overview_widths = [0.12, 0.16]
    if show_electric_storage:
        overview_headers.append("Stromspeicher")
        overview_widths.append(0.12 if show_heat_storage else 0.14)
    if show_heat_storage:
        overview_headers.append("Wärmespeicher")
        overview_widths.append(0.12 if show_electric_storage else 0.14)
    overview_headers.extend(["Gesamtkosten", "Investition", "Emissionen", "Strom-Autarkie"])
    if show_electric_storage and show_heat_storage:
        overview_widths.extend([0.16, 0.15, 0.11, 0.12])
    elif show_electric_storage or show_heat_storage:
        overview_widths.extend([0.17, 0.16, 0.14, 0.14])
    else:
        overview_widths.extend([0.20, 0.18, 0.16, 0.18])
    overview_table = _matrix_table(
        overview_headers,
        overview_rows,
        overview_widths,
    )
    if overview_table is not None:
        story.append(overview_table)
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Gesamtkosten = annualisierte CAPEX + OPEX einschließlich CO2-Kosten.",
            small_style,
        ))

    story.append(Spacer(1, 14))
    story.append(Paragraph("Inhaltsverzeichnis", h1_style))
    story.append(Paragraph(
        "Die folgenden Kapitel orientieren sich an einer fachlichen Leselogik vom Systemüberblick über Dimensionierung und Betrieb bis hin zu Wirtschaftlichkeit, Emissionen und methodischer Einordnung.",
        body_style,
    ))
    toc_table = _matrix_table(
        ["Abschnitt", "Inhalt"],
        toc_rows,
        [0.42, 0.58],
    )
    if toc_table is not None:
        story.append(toc_table)

    if has_map_section:
        story.append(PageBreak())
        story.append(Paragraph(f"{section_numbers['system']}. Systembeschreibung und räumliche Einordnung", h1_style))
        story.append(Paragraph(
            "Die Systemkarte zeigt die im Exportumfang enthaltenen georeferenzierten Anlagen und Standorte. "
            f"Die Darstellung nutzt dieselbe OpenStreetMap-Grundlage wie die Dashboard-Ansicht und übernimmt die dort verwendeten Markersymbole. Lizenz- und Copyright-Hinweise zur Kartengrundlage: {OSM_COPYRIGHT_URL}. Die interaktive Einbindung im Dashboard erfolgt mit Leaflet.",
            body_style,
        ))
        map_info_table = _kv_table(map_overview_rows, key_ratio=0.40)
        if map_info_table is not None:
            story.append(map_info_table)
            story.append(Spacer(1, 8))
            story.append(Paragraph(
                "Gezählt werden im Bericht nur eindeutige georeferenzierte Anlagen bzw. Standorte. Sammelmarker fassen ausschließlich verschiedene Anlagen am exakt selben Ort zusammen; periodische Varianten derselben Anlage werden nicht mehrfach gezählt.",
                small_style,
            ))
        _append_optional_figure(
            story,
            "Systemkarte",
            map_fig,
            "Systemkarte",
            f"Die Abbildung zeigt die im Export berücksichtigten Komponenten auf derselben Kartenbasis wie die Dashboard-Systemkarte. {OSM_ATTRIBUTION_TEXT}.",
            135,
            has_content=not df_map_plot.empty,
            missing_reason="Im gewählten Exportumfang liegen keine georeferenzierten Komponenten vor.",
        )

    if has_capacity_section:
        story.append(PageBreak())
        story.append(Paragraph(f"{section_numbers['capacity']}. Dimensionierung und Ausbau", h1_style))
        capacity_headers = ["Periode", "Sektor", "Installierte Leistung"]
        capacity_widths = [0.11, 0.12, 0.18]
        if show_electric_storage:
            capacity_headers.append("Stromspeicher")
            capacity_widths.append(0.15)
        if show_heat_storage:
            capacity_headers.append("Wärmespeicher")
            capacity_widths.append(0.15)
        capacity_headers.append("Dominante Technologien")
        capacity_widths.append(max(0.19, 1.0 - sum(capacity_widths)))
        capacity_table = _matrix_table(
            capacity_headers,
            capacity_rows,
            capacity_widths,
        )
        if capacity_table is not None:
            story.append(capacity_table)
            story.append(Spacer(1, 8))
        _append_optional_figure(
            story,
            "Nennleistungen",
            capacity_power_fig,
            "Nennleistungen nach Periode und Sektor",
            "Die Darstellung berücksichtigt nur installierte Leistungsanteile der vor Ort wirksamen Erzeugungs- und Umwandlungstechnik sowie gegebenenfalls Fernwärmebezug. Netzbezug, Einspeisung, Gasnetzbezug und Speicherleistung werden nicht berücksichtigt.",
            92,
            has_content=_report_has_positive_values(df_power_scope, "p_nom"),
            missing_reason="Für die gewählten Perioden und Sektoren liegen keine installierten Leistungen vor.",
        )
        _append_optional_figure(
            story,
            "Speicherkapazitäten",
            capacity_energy_fig,
            "Speicherkapazitäten nach Periode und Sektor",
            "",
            92,
            has_content=_report_has_positive_values(df_energy_scope, "e_nom"),
            missing_reason="Für die gewählten Perioden und Sektoren liegen keine Speicherkapazitäten vor.",
        )

    if has_ops_section:
        story.append(PageBreak())
        story.append(Paragraph(f"{section_numbers['ops']}. Betriebliche Ergebnisse", h1_style))
        ops_table = _matrix_table(
            ["Periode", "Strom-Autarkie", "Wärme-Autarkie", "PV-Eigenverbrauch", "PV-Einspeisequote"],
            ops_summary_rows,
            [0.16, 0.21, 0.21, 0.21, 0.21],
        )
        if ops_table is not None:
            story.append(ops_table)
            story.append(Spacer(1, 5))
        peak_table = _matrix_table(
            ["Periode", "Peak Gesamtstromlast", "Peak Reststromlast", "Peak Wärmelast"],
            ops_peak_rows,
            [0.16, 0.28, 0.28, 0.28],
        )
        if peak_table is not None:
            story.append(peak_table)
            story.append(Spacer(1, 5))
        specific_cost_table = _matrix_table(
            ["Periode", "LCOE Strom", "LCOH Wärme", "LCOS Speicher"],
            ops_specific_cost_rows,
            [0.16, 0.28, 0.28, 0.28],
        )
        if specific_cost_table is not None:
            story.append(specific_cost_table)

    if has_cost_section:
        if not has_ops_section:
            story.append(PageBreak())
        else:
            story.append(Spacer(1, 14))
        story.append(Paragraph(f"{section_numbers['cost']}. Wirtschaftliche Ergebnisse", h1_style))
        story.append(Paragraph(
            "Gesamtkosten = annualisierte CAPEX + OPEX einschließlich CO2-Kosten.",
            small_style,
        ))
        cost_table = _matrix_table(
            ["Periode", "Gesamtkosten", "CAPEX (ann.)", "OPEX inkl. CO2", "CO2-Kosten", "Investition"],
            cost_rows,
            [0.13, 0.18, 0.16, 0.20, 0.15, 0.18],
        )
        if cost_table is not None:
            story.append(cost_table)

    if has_emission_section:
        if has_cost_section or has_ops_section:
            story.append(Spacer(1, 14))
        else:
            story.append(PageBreak())
        story.append(Paragraph(f"{section_numbers['co2']}. Emissionsbezogene Ergebnisse", h1_style))
        story.append(Paragraph(
            "Die Emissionsauswertung ordnet Emissionen und CO2-bezogene Kosten dem gewählten Exportumfang zu. "
            "Für eine schnelle fachliche Einordnung wird zusätzlich der jeweils größte Emissionsbeitrag pro Periode ausgewiesen.",
            body_style,
        ))
        emission_table = _matrix_table(
            ["Periode", "Emissionen", "CO2-Preis", "CO2-Kosten", "Größter Beitrag"],
            emission_rows,
            [0.12, 0.18, 0.15, 0.17, 0.38],
        )
        if emission_table is not None:
            story.append(emission_table)

    story.append(PageBreak())
    story.append(Paragraph(f"{section_numbers['methods']}. Methodische Hinweise", h1_style))
    notes = [
        f"Der Bericht basiert auf derselben serverseitigen Daten- und Kennzahlenlogik wie das Dashboard. Exportiert werden die Perioden {_report_scope_label(selected_periods)} und die Sektoren {export_sector_label}.",
        "Bei Mehrperiodenmodellen sind die ausgewiesenen Werte als repräsentative Jahreswerte der jeweiligen Investitionsperiode zu lesen. Zwischenjahre werden dadurch nicht als eigenständige Kalendersimulationen abgebildet.",
        f"Die Systemkarte ist eine statische Berichtsdarstellung. Wenn der Kartenhintergrund im Exportumfeld geladen werden kann, basiert er auf OpenStreetMap ({OSM_COPYRIGHT_URL}); die interaktive Dashboard-Karte wird mit Leaflet eingebunden. Andernfalls wird auf eine schematische Koordinatendarstellung zurückgegriffen.",
        "Die ausgewiesenen Gesamtkosten entsprechen im Dashboard den annualisierten CAPEX zuzüglich OPEX einschließlich CO2-Kosten. LCOE, LCOH und LCOS werden aus derselben Kosten- und Energiemengenlogik abgeleitet.",
        "Emissionskennzahlen bilden ausschließlich die im Modell hinterlegten Emissionsfaktoren und CO2-Preise ab. Der Bericht ist daher kein vollständiger THG-Inventarbericht im Sinne einer eigenständigen Bilanzierungsmethodik.",
        "Diagramme ohne inhaltlich auswertbare Daten werden nicht in den Bericht aufgenommen. Stattdessen werden sie am Ende unter den Export-Hinweisen mit Begründung dokumentiert.",
    ]
    for note in notes:
        story.append(Paragraph(html_escape(note), body_style))

    if warnings:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Export-Hinweise", h2_style))
        for warning in warnings:
            story.append(Paragraph(html_escape(warning), small_style))

    class _NumberedCanvas(pdf_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            """
            Initialisiert den PDF-Canvas und sammelt Seitenzustände für die spätere Nummerierung.
            
            Inputs: self, *args, **kwargs.
            Outputs: Inplace-Anpassung oder keine Rückgabe.
            """
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            """
            Puffert eine PDF-Seite, damit die Gesamtseitenzahl im Footer bekannt ist.
            
            Inputs: self.
            Outputs: Inplace-Anpassung oder keine Rückgabe.
            """
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            """
            Schreibt alle gepufferten Seiten mit Footer und Seitenzählung in die PDF-Datei.
            
            Inputs: self.
            Outputs: Inplace-Anpassung oder keine Rückgabe.
            """
            page_count = max(1, len(self._saved_page_states))
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_footer(page_count)
                pdf_canvas.Canvas.showPage(self)
            pdf_canvas.Canvas.save(self)

        def _draw_footer(self, page_count: int):
            """
            Zeichnet Berichtstitel und Seitenzahl in den Fußbereich jeder PDF-Seite.
            
            Inputs: self, page_count.
            Outputs: Inplace-Anpassung oder keine Rückgabe.
            """
            self.saveState()
            self.setStrokeColor(colors.HexColor("#d8dee6"))
            self.setLineWidth(0.5)
            self.line(doc.leftMargin, 14 * mm, doc.leftMargin + doc.width, 14 * mm)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#6b7280"))
            self.drawString(doc.leftMargin, 9.5 * mm, f"Energiebericht - {dataset_name}")
            self.drawRightString(
                doc.leftMargin + doc.width,
                9.5 * mm,
                f"Seite {self._pageNumber} von {page_count}",
            )
            self.restoreState()

    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue(), warnings


@app.callback(
    Output("report-export-period-values", "options"),
    Output("report-export-period-values", "value"),
    Output("report-export-sector-values", "options"),
    Output("report-export-sector-values", "value"),
    Output("report-export-period-mode", "value"),
    Output("report-export-sector-mode", "value"),
    Input("datafile-dropdown", "value"),
)
def sync_report_export_controls(nc_path):
    """
    Aktualisiert die Export-Filter für den PDF-Bericht, sobald eine .nc-Datei ausgewählt wurde.
    
    Inputs: nc_path.
    Outputs: synchronisierte Dropdownwerte, Optionen oder Layoutzustände.
    """
    if not nc_path:
        return [], [], [], [], "all", "all"

    st = get_dataset_state_fresh(nc_path)
    if not st.get("ok", False):
        return [], [], [], [], "all", "all"

    periods = _report_available_periods(st)
    sectors = _report_available_export_sectors(st)
    period_options = [{"label": str(period), "value": str(period)} for period in periods]
    sector_options = [{"label": str(sector), "value": str(sector)} for sector in sectors]
    return period_options, periods, sector_options, sectors, "all", "all"


@app.callback(
    Output("report-export-period-values-wrap", "style"),
    Output("report-export-sector-values-wrap", "style"),
    Input("report-export-period-mode", "value"),
    Input("report-export-sector-mode", "value"),
)
def toggle_report_export_specific_inputs(period_mode, sector_mode):
    """
    Steuert, die Sichtbarkeit der Auswahlfelder für Perioden und Sektoren des Filters für den PDF-Bericht.
    
    Inputs: period_mode, sector_mode.
    Outputs: Sichtbare oder ausgeblendete UI-Elemente.
    """
    period_style = {"display": "block", "marginBottom": "10px"} if str(period_mode) == "specific" else {"display": "none", "marginBottom": "10px"}
    sector_style = {"display": "block", "marginBottom": "12px"} if str(sector_mode) == "specific" else {"display": "none", "marginBottom": "12px"}
    return period_style, sector_style


@app.callback(
    Output("report-export-panel", "style"),
    Output("report-export-status", "children"),
    Input("report-export-button", "n_clicks"),
    Input("report-export-cancel-button", "n_clicks"),
    Input("report-export-confirm-button", "n_clicks"),
    State("datafile-dropdown", "value"),
    State("report-export-period-mode", "value"),
    State("report-export-period-values", "value"),
    State("report-export-sector-mode", "value"),
    State("report-export-sector-values", "value"),
    State("map-component-dropdown", "value"),
    prevent_initial_call=True,
)
def export_pdf_report(
    open_clicks,
    cancel_clicks,
    confirm_clicks,
    nc_path,
    export_period_mode,
    export_period_values,
    export_sector_mode,
    export_sector_values,
    map_components,
):
    """
    Öffnet oder schließt das PDF-Exportpanel, prüft die Nutzerauswahl, erzeugt den PDF-Bericht, 
    speichert ihn als Datei und zeigt anschließend eine Erfolgs- oder Fehlermeldung im Dashboard an.
    
    Inputs: open_clicks, cancel_clicks, confirm_clicks, nc_path, export_period_mode, export_period_values, export_sector_mode, export_sector_values, map_components.
    Outputs: Export-Meldung für den Nutzer.
    """
    hidden_style = {
        "display": "none",
        "width": "360px",
        "padding": "12px",
        "border": "1px solid #d8dee6",
        "borderRadius": "8px",
        "backgroundColor": "#f8fafc",
        "boxShadow": "0 4px 12px rgba(15, 53, 84, 0.08)",
        "marginTop": "6px",
        "position": "relative",
        "zIndex": 6000,
    }
    visible_style = dict(hidden_style)
    visible_style["display"] = "block"

    trigger = ctx.triggered_id
    if trigger == "report-export-button":
        if not nc_path:
            return hidden_style, "Keine Datenbasis ausgewählt."
        return visible_style, no_update

    if trigger == "report-export-cancel-button":
        return hidden_style, no_update

    if trigger != "report-export-confirm-button":
        return no_update, no_update

    if not nc_path:
        return visible_style, "Keine Datenbasis ausgewählt."

    st = get_dataset_state_fresh(nc_path)
    if not st.get("ok", False):
        return visible_style, f"PDF-Bericht konnte nicht erzeugt werden: {st.get('reason', 'Unbekannter Fehler')}."

    selections = _report_export_scope_selections(
        st,
        export_period_mode=export_period_mode,
        export_period_values=export_period_values,
        export_sector_mode=export_sector_mode,
        export_sector_values=export_sector_values,
        map_components=map_components,
    )

    if str(export_period_mode) == "specific" and not selections.get("export_periods"):
        return visible_style, "Bitte mindestens eine Periode auswählen."
    if str(export_sector_mode) == "specific" and not selections.get("export_sectors"):
        return visible_style, "Bitte mindestens einen Sektor auswählen."

    try:
        pdf_bytes, warnings = _build_pdf_report_bytes_scientific_v2(nc_path, st, selections)
    except Exception as exc:
        return visible_style, f"PDF-Bericht konnte nicht erzeugt werden: {exc}"

    base_name = os.path.splitext(_basename(nc_path))[0]
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", base_name).strip("_") or "energiebericht"
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{safe_name}_Energiebericht_{stamp}.pdf"
    try:
        output_path, save_mode = _report_save_pdf_to_disk(pdf_bytes, filename)
    except Exception as exc:
        return visible_style, f"PDF-Bericht konnte nicht gespeichert werden: {exc}"

    if warnings:
        if save_mode == "downloads":
            status = (
                f"PDF-Bericht gespeichert unter: {output_path}. "
                f"{len(warnings)} Export-Hinweis(e) wurden im Bericht dokumentiert."
            )
        else:
            status = (
                f"PDF-Bericht konnte nicht in Downloads gespeichert werden und liegt stattdessen unter: {output_path}. "
                f"{len(warnings)} Export-Hinweis(e) wurden im Bericht dokumentiert."
            )
    else:
        if save_mode == "downloads":
            status = f"PDF-Bericht gespeichert unter: {output_path}."
        else:
            status = f"PDF-Bericht konnte nicht in Downloads gespeichert werden und liegt stattdessen unter: {output_path}."

    return hidden_style, status

#%% Dash App (Layout)

nc_files = list_nc_files(DATA_DIR)
file_options = [{"label": os.path.basename(p), "value": p} for p in nc_files]
default_file = file_options[0]["value"] if file_options else None

# Positionen für die Filterleiste
FILTER_SIDEBAR_WIDTH = "280px"
FILTER_SIDEBAR_FIXED_TOP = "190px"
FILTER_SIDEBAR_TOP_VAR = "var(--filter-sidebar-top, 190px)"

# Einheitlicher Seitenaufbau: Filterleiste ist rechts am Bildschirm fixiert und bleibt beim Scrollen unterhalb des Registerkartenbandes sichtbar.
FILTER_SIDEBAR_BASE_STYLE = {
    "flex": f"0 0 {FILTER_SIDEBAR_WIDTH}",
    "width": FILTER_SIDEBAR_WIDTH,
    "borderLeft": "1px solid #ddd",
    "paddingLeft": "12px",
    "boxSizing": "border-box",
    "alignSelf": "flex-start",
    "position": "fixed",
    "right": "12px",
    "top": FILTER_SIDEBAR_TOP_VAR,
    "maxHeight": f"calc(100vh - {FILTER_SIDEBAR_TOP_VAR} - 12px)",
    "overflowY": "auto",
    "backgroundColor": "white",
    "zIndex": 2000,
}

FILTER_CONTENT_ROW_STYLE = {
    "display": "flex",
    "gap": "16px",
    "alignItems": "flex-start",
    "overflow": "visible",
    "paddingRight": f"calc({FILTER_SIDEBAR_WIDTH} + 16px)",
    "boxSizing": "border-box",
}


def filter_sidebar_style(visible: bool = True) -> dict:
    """
    Erstellt den CSS-Stil für die rechts fixierte Filterleiste.
    
    Inputs: visible.
    Outputs: CSS-Style-Dict für sichtbare oder ausgeblendete Filterbereiche.
    """
    style = FILTER_SIDEBAR_BASE_STYLE.copy()
    style["display"] = "block" if visible else "none"
    return style

# Aufbau von: Dashboard-Titel, Datenbasis-Dropdown, PDF-Bericht-erstellen-Button, Auswahl für Perioden, Auswahl für Sektoren etc.
app.layout = html.Div(
    style={"padding": "12px", "fontFamily": BODY_FONT_FAMILY, "fontSize": f"{BASE_FONT_SIZE_PX}px"},
    children=[
        html.Div(
            style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "gap": "16px"},
            children=[
                html.H2("Dashboard", style={"margin": 0}),
                html.Div(
                    style={"display": "flex", "alignItems": "flex-start", "gap": "12px"},
                    children=[
                        html.Div(
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "gap": "8px",
                                "position": "relative",
                                "zIndex": 5000,
                            },
                            children=[
                                html.Label("Datenbasis", style={"margin": 0}),
                                dcc.Dropdown(
                                    id="datafile-dropdown",
                                    options=file_options,
                                    value=default_file,
                                    clearable=False,
                                    style={"width": "420px"},
                                    placeholder="Keine .nc-Dateien gefunden",
                                ),
                            ],
                        ),
                        html.Div(
                            style={"display": "flex", "flexDirection": "column", "alignItems": "flex-start", "gap": "4px"},
                            children=[
                                html.Button(
                                    "PDF-Bericht erstellen",
                                    id="report-export-button",
                                    n_clicks=0,
                                    style={
                                        "backgroundColor": "#0f3554",
                                        "color": "white",
                                        "border": "none",
                                        "borderRadius": "4px",
                                        "padding": "10px 14px",
                                        "cursor": "pointer",
                                        "fontWeight": "600",
                                        "whiteSpace": "nowrap",
                                    },
                                ),
                                html.Div(
                                    id="report-export-status",
                                    style={
                                        "fontSize": "0.85rem",
                                        "color": "#555",
                                        "lineHeight": "1.3",
                                        "maxWidth": "360px",
                                    },
                                ),
                                html.Div(
                                    id="report-export-panel",
                                    style={
                                        "display": "none",
                                        "width": "360px",
                                        "padding": "12px",
                                        "border": "1px solid #d8dee6",
                                        "borderRadius": "8px",
                                        "backgroundColor": "#f8fafc",
                                        "boxShadow": "0 4px 12px rgba(15, 53, 84, 0.08)",
                                        "marginTop": "6px",
                                        "position": "relative",
                                        "zIndex": 6000,
                                    },
                                    children=[
                                        html.Div(
                                            "Berichtsumfang auswählen",
                                            style={"fontWeight": "700", "color": "#0f3554", "marginBottom": "10px"},
                                        ),
                                        html.Label("Perioden", style={"fontWeight": "600"}),
                                        dcc.RadioItems(
                                            id="report-export-period-mode",
                                            options=[
                                                {"label": "Alle Perioden", "value": "all"},
                                                {"label": "Spezifische Perioden", "value": "specific"},
                                            ],
                                            value="all",
                                            labelStyle={"display": "block", "marginBottom": "4px"},
                                            style={"marginBottom": "8px"},
                                        ),
                                        html.Div(
                                            id="report-export-period-values-wrap",
                                            style={"display": "none", "marginBottom": "10px"},
                                            children=[
                                                dcc.Checklist(
                                                    id="report-export-period-values",
                                                    options=[],
                                                    value=[],
                                                    labelStyle={"display": "block", "marginBottom": "3px"},
                                                    inputStyle={"marginRight": "6px"},
                                                ),
                                            ],
                                        ),
                                        html.Label("Sektoren", style={"fontWeight": "600"}),
                                        dcc.RadioItems(
                                            id="report-export-sector-mode",
                                            options=[
                                                {"label": "Alle verfügbaren Sektoren", "value": "all"},
                                                {"label": "Spezifische Sektoren", "value": "specific"},
                                            ],
                                            value="all",
                                            labelStyle={"display": "block", "marginBottom": "4px"},
                                            style={"marginBottom": "8px"},
                                        ),
                                        html.Div(
                                            id="report-export-sector-values-wrap",
                                            style={"display": "none", "marginBottom": "12px"},
                                            children=[
                                                dcc.Checklist(
                                                    id="report-export-sector-values",
                                                    options=[],
                                                    value=[],
                                                    labelStyle={"display": "block", "marginBottom": "3px"},
                                                    inputStyle={"marginRight": "6px"},
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"display": "flex", "gap": "8px"},
                                            children=[
                                                html.Button(
                                                    "Bericht jetzt erzeugen",
                                                    id="report-export-confirm-button",
                                                    n_clicks=0,
                                                    style={
                                                        "backgroundColor": "#0f3554",
                                                        "color": "white",
                                                        "border": "none",
                                                        "borderRadius": "4px",
                                                        "padding": "8px 12px",
                                                        "cursor": "pointer",
                                                        "fontWeight": "600",
                                                    },
                                                ),
                                                html.Button(
                                                    "Abbrechen",
                                                    id="report-export-cancel-button",
                                                    n_clicks=0,
                                                    style={
                                                        "backgroundColor": "#e5e7eb",
                                                        "color": "#334155",
                                                        "border": "none",
                                                        "borderRadius": "4px",
                                                        "padding": "8px 12px",
                                                        "cursor": "pointer",
                                                    },
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        html.Hr(),

        # Erzeugt den Dashboard-Tab für Speicherkapazitäten
        dcc.Tabs(
            id="main-tabs",
            value="tab-cap",
            children=[
                dcc.Tab(
                    id="tab-cap",
                    label="Leistungen / Kapazitäten",
                    value="tab-cap",
                    children=[
                        html.Div(
                            style=FILTER_CONTENT_ROW_STYLE,
                            children=[
                                html.Div(
                                    style={"flex": "1"},
                                    children=[
                                        html.H3("Nennleistungen"),
                                        dcc.Graph(id="cap-power-graph", style={"height": "clamp(360px, 48vh, 520px)"}),
                                        html.H3("Speicherkapazitäten"),
                                        dcc.Graph(id="cap-energy-graph", style={"height": "clamp(360px, 48vh, 520px)"}),
                                    ],
                                ),
                                html.Div(
                                    className="filter-sidebar",
                                    style=filter_sidebar_style(True),
                                    children=[
                                        html.H4("Filter"),
                                        html.Label("Sektor"),
                                        dcc.Dropdown(
                                            id="cap-sector-dropdown",
                                            options=[{"label": s, "value": s} for s in SECTORS],
                                            value="Sonstige",
                                            clearable=False,
                                        ),
                                        html.Div(
                                            id="cap-year-filter",
                                            style={"display": "none", "marginTop": "12px"},
                                            children=[
                                                html.Label("Investitionsperiode"),
                                                dcc.Dropdown(
                                                    id="cap-year-dropdown",
                                                    options=[],
                                                    value="all",
                                                    multi=False,
                                                    clearable=False,
                                                    placeholder="Alle Perioden",
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

                # Erzeugt den Dashboard-Tab für Zeitreihen
                dcc.Tab(
                    id="tab-ts",
                    label="Zeitreihen",
                    value="tab-ts",
                    children=[
                        html.Div(
                            style=FILTER_CONTENT_ROW_STYLE,
                            children=[
                                html.Div(
                                    style={"flex": "1"},
                                    children=[
                                        html.H3("Zeitreihen nach Sektor und Investitionsperiode"),
                                        dcc.Graph(id="ts-strom-graph", style={"height": "420px"}),
                                        dcc.Graph(id="ts-waerme-graph", style={"height": "420px"}),
                                        dcc.Graph(id="ts-sonst-graph", style={"height": "420px"}),
                                    ],
                                ),
                                html.Div(
                                    id="ts-filter-container",
                                    className="filter-sidebar",
                                    style=filter_sidebar_style(False),
                                    children=[
                                        html.H4("Filter"),
                                        html.Label("Investitionsperiode"),
                                        dcc.Dropdown(
                                            id="ts-period-dropdown",
                                            options=[{"label": "Single", "value": "Single"}],
                                            value="Single",
                                            clearable=False,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

                # Erzeugt den Dashboard-Tab für Autarkie, Laskennzahlen, PV-Kennzahlen, Deckungsanteile etc.
                dcc.Tab(
                    id="tab-ops",
                    label="Betriebsanalyse",
                    value="tab-ops",
                    disabled=True,
                    children=[
                        html.Div(
                            style=FILTER_CONTENT_ROW_STYLE,
                            children=[
                                html.Div(
                                    style={"flex": "1", "minWidth": 0},
                                    children=[
                                        register_agenda([
                                            ("ops-autarky-section", "Autarkie & Eigenverbrauch"),
                                            ("ops-load-metrics-section", "Lastkennzahlen"),
                                            ("ops-load-duration-section", "Lastdauerlinie"),
                                            ("ops-pv-usage-section", "PV-Eigenverbrauch, Einspeisung und Strombezug"),
                                            ("ops-share-electric-section", "Deckungsanteile Strom"),
                                            ("ops-share-heat-section", "Deckungsanteile Wärme"),
                                        ]),
                                        diagram_anchor("ops-autarky-section", "Autarkie & Eigenverbrauch"),
                                        dcc.Graph(id="ops-autarky-graph", style={"height": "420px"}),
                                        diagram_anchor("ops-load-metrics-section", "Lastkennzahlen"),
                                        dcc.Graph(id="ops-load-metrics-table", style={"height": "500px"}),
                                        scroll_anchor("ops-load-duration-section"),
                                        dcc.Graph(id="ops-load-duration-graph", style={"height": "480px"}),
                                        diagram_anchor("ops-pv-usage-section", "PV-Nutzung und Deckungsanteile"),
                                        period_filter_note("Hinweis: PV-Nutzung und Deckungsanteile werden periodenübergreifend dargestellt. Der Periodenfilter wirkt daher nicht auf diese Diagramme."),
                                        html.Div(
                                            style={"display": "flex", "gap": "16px", "alignItems": "flex-start"},
                                            children=[
                                                html.Div(
                                                    style={"flex": "1", "minWidth": 0},
                                                    children=[
                                                        dcc.Graph(id="ops-pv-usage-graph", style={"height": "430px"}),
                                                    ],
                                                ),
                                                html.Div(
                                                    style={"flex": "1", "minWidth": 0},
                                                    children=[
                                                        scroll_anchor("ops-share-electric-section"),
                                                        dcc.Graph(id="ops-technology-share-electric-graph", style={"height": "460px"}),
                                                    ],
                                                ),
                                                html.Div(
                                                    style={"flex": "1", "minWidth": 0},
                                                    children=[
                                                        scroll_anchor("ops-share-heat-section"),
                                                        dcc.Graph(id="ops-technology-share-heat-graph", style={"height": "460px"}),
                                                    ],
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="filter-sidebar",
                                    style=filter_sidebar_style(True),
                                    children=[
                                        html.H4("Filter"),
                                        html.Label("Investitionsperiode"),
                                        dcc.Dropdown(
                                            id="ops-period-dropdown",
                                            options=[{"label": "Single", "value": "Single"}],
                                            value="Single",
                                            clearable=False,
                                        ),
                                        html.Hr(),
                                        html.Div(
                                            "Autarkiewerte werden bilanziell aus Netzbezug, externer Wärmebereitstellung und Endlasten berechnet.",
                                            style={"color": "#555", "fontSize": "0.9rem", "lineHeight": "1.35"},
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

                # Erzeugt den Dashboard-Tab für Ausbaupfad und Lebensdauern
                dcc.Tab(
                    id="tab-exp",
                    label="Ausbaupfad / Lebensdauer",
                    value="tab-exp",
                    disabled=True,
                    children=[
                        html.Div(
                            style=FILTER_CONTENT_ROW_STYLE,
                            children=[
                                html.Div(
                                    style={"flex": "1", "minWidth": 0},
                                    children=[
                                        html.H3("Ausbaupfad"),
                                        period_filter_note("Hinweis: Ausbaupfad und Lebensdauer zeigen den gesamten Investitionsverlauf. Der Periodenfilter ist deshalb in diesem Modul deaktiviert."),
                                        dcc.Graph(id="exp-path-graph", style={"height": "520px"}),
                                        html.Hr(),
                                        html.H3("Lebensdauer / Aktivitätszeitraum"),
                                        dcc.Graph(id="exp-life-graph", style={"height": "650px"}),
                                    ],
                                ),
                                html.Div(
                                    className="filter-sidebar",
                                    style=filter_sidebar_style(True),
                                    children=[
                                        html.H4("Filter"),
                                        html.Label("Sektor"),
                                        dcc.Dropdown(
                                            id="exp-sector-dropdown",
                                            options=[{"label": s, "value": s} for s in SECTORS],
                                            value="Sonstige",
                                            clearable=False,
                                        ),
                                        html.Hr(),
                                        html.Label("Investitionsperiode"),
                                        dcc.Dropdown(
                                            id="exp-period-dropdown",
                                            options=[{"label": "Alle Perioden", "value": "all"}],
                                            value="all",
                                            clearable=False,
                                            disabled=True,
                                        ),
                                        period_filter_note("Der Periodenfilter hat hier keine Wirkung, weil der Ausbaupfad alle Investitionsperioden abbildet."),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

                # Erzeugt den Dashboard-Tab für das Sankey-Diagramm
                dcc.Tab(
                    id="tab-sankey",
                    label="Sankey-Diagramm (Energieflüsse)",
                    value="tab-sankey",
                    children=[
                        html.Div(
                            style=FILTER_CONTENT_ROW_STYLE,
                            children=[
                                html.Div(
                                    style={"flex": "1", "minWidth": 0},
                                    children=[
                                        dcc.Graph(id="sankey-graph", style={"height": "780px"}),
                                    ],
                                ),
                                html.Div(
                                    id="sankey-filter-container",
                                    className="filter-sidebar",
                                    style=filter_sidebar_style(False),
                                    children=[
                                        html.H4("Filter"),
                                        html.Label("Investitionsperiode"),
                                        dcc.Dropdown(
                                            id="sankey-period-dropdown",
                                            options=[{"label": "Single", "value": "Single"}],
                                            value="Single",
                                            clearable=False,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

                # Erzeugt den Dashboard-Tab für die räumliche Systemkarte
                dcc.Tab(
                    id="tab-map",
                    label="Systemkarte",
                    value="tab-map",
                    disabled=True,
                    children=[
                        html.Div(
                            style=FILTER_CONTENT_ROW_STYLE,
                            children=[
                                html.Div(
                                    style={"flex": "1", "minWidth": 0},
                                    children=[
                                        html.Iframe(
                                            id="network-map-graph",
                                            style={
                                                "height": f"{MAP_FIGURE_HEIGHT}px",
                                                "width": "100%",
                                                "border": "0",
                                            },
                                            sandbox="allow-scripts allow-same-origin",
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="filter-sidebar",
                                    style=filter_sidebar_style(True),
                                    children=[
                                        html.H4("Filter"),
                                        html.Div(
                                            id="map-period-container",
                                            style={"display": "none", "marginBottom": "12px"},
                                            children=[
                                                html.Label("Investitionsperiode"),
                                                dcc.Dropdown(
                                                    id="map-period-dropdown",
                                                    options=[{"label": "Alle Perioden", "value": "all"}],
                                                    value="all",
                                                    clearable=False,
                                                ),
                                            ],
                                        ),
                                        html.Label("Komponentenfilter"),
                                        dcc.Dropdown(
                                            id="map-component-dropdown",
                                            options=[],
                                            value=[],
                                            multi=True,
                                            placeholder="Alle sichtbaren Komponenten",
                                        ),
                                        html.Hr(),
                                        html.Div(
                                            "CRS: EPSG:4326 (WGS 84), x=Longitude, y=Latitude. Quelle und Lagegenauigkeit stehen im Hover.",
                                            style={"color": "#555", "fontSize": "0.9rem", "lineHeight": "1.35"},
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

                # Erzeugt den Dashboard-Tab für die CO2-Auswertung
                dcc.Tab(
                    id="tab-co2",
                    label="CO2 / Emissionen",
                    value="tab-co2",
                    disabled=True,
                    children=[
                        html.Div(
                            style=FILTER_CONTENT_ROW_STYLE,
                            children=[
                                html.Div(
                                    style={"flex": "1", "minWidth": 0},
                                    children=[
                                        html.P(
                                            "Hinweis: Die CO2-Auswertung zeigt Jahreswerte des repräsentativen "
                                            "Investitionsjahres. Die Diagramme bilden alle Investitionsperioden gemeinsam ab.",
                                            style={"marginTop": "0", "color": "#555", "fontSize": "0.95rem"},
                                        ),
                                        html.H3("CO2-Emissionen nach Scope je Investitionsperiode (Jahreswert)"),
                                        dcc.Graph(id="co2-period-totals-graph", style={"height": "380px"}),
                                        html.H3("CO2-Kosten nach Scope je Investitionsperiode (Jahreswert)"),
                                        dcc.Graph(id="co2-cost-totals-graph", style={"height": "380px"}),
                                        html.H3("CO2-Intensitäten"),
                                        dcc.Graph(id="co2-intensity-graph", style={"height": "380px"}),
                                    ],
                                ),
                                html.Div(
                                    className="filter-sidebar",
                                    style=filter_sidebar_style(True),
                                    children=[
                                        html.H4("Filter"),
                                        html.Label("Investitionsperiode"),
                                        dcc.Dropdown(
                                            id="co2-period-dropdown",
                                            options=[{"label": "Alle Perioden", "value": "all"}],
                                            value="all",
                                            clearable=False,
                                            disabled=True,
                                        ),
                                        period_filter_note("Der Periodenfilter ist deaktiviert, weil die CO2-Diagramme alle Investitionsperioden gemeinsam darstellen."),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

                # Erzeugt den Dashboard-Tab für die Wirtschaftsanalyse
                dcc.Tab(
                    id="tab-cost",
                    label="Wirtschaftlichkeit",
                    value="tab-cost",
                    disabled=True,
                    children=[
                        html.Div(
                            style=FILTER_CONTENT_ROW_STYLE,
                            children=[
                                html.Div(
                                    style={"flex": "1", "minWidth": 0},
                                    children=[
                                        register_agenda([
                                            ("cost-cashflow-section", "Jährliche Kostenentwicklung"),
                                            ("cost-investment-section", "Gesamtinvestitionen"),
                                            ("cost-composition-section", "Gesamtkostenverteilung"),
                                            ("cost-pie-section", "Gesamtkostenstruktur"),
                                            ("cost-lcoe-section", "Stromgestehungskosten (LCOE)"),
                                            ("cost-lcoh-section", "Wärmegestehungskosten (LCOH)"),
                                            ("cost-lcos-section", "Spezifische Speicherkosten (LCOS)"),
                                        ]),
                                        diagram_anchor("cost-cashflow-section", "Jährliche Kostenentwicklung (CAPEX = Investitionskosten als Annuität; OPEX = Betriebskosten)"),
                                        dcc.Graph(id="cost-cashflow-graph", style={"height": "460px"}),
                                        diagram_anchor("cost-investment-section", "Gesamtinvestitionen (CAPEX, nicht annuisiert)"),
                                        dcc.Graph(id="cost-investment-capex-graph", style={"height": "420px"}),
                                        diagram_anchor("cost-composition-section", "Gesamtkostenverteilung (CAPEX und OPEX)"),
                                        dcc.Graph(id="cost-composition-graph", style={"height": "520px"}),
                                        diagram_anchor("cost-pie-section", "Gesamtkostenstruktur (CAPEX und OPEX)"),
                                        dcc.Graph(id="cost-total-pie-graph", style={"height": "420px"}),
                                        diagram_anchor("cost-lcoe-section", "Stromgestehungskosten (LCOE)"),
                                        dcc.Graph(id="cost-lcoe-tech-graph", style={"height": "420px"}),
                                        diagram_anchor("cost-lcoh-section", "Wärmegestehungskosten (LCOH)"),
                                        dcc.Graph(id="cost-heat-tech-graph", style={"height": "420px"}),
                                        diagram_anchor("cost-lcos-section", "Spezifische Speicherkosten (LCOS)"),
                                        dcc.Graph(id="cost-lcos-graph", style={"height": "420px"}),
                                        html.Div(
                                            style={"display": "none"},
                                            children=[dcc.Graph(id="cost-period-totals-graph")],
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="filter-sidebar",
                                    style=filter_sidebar_style(True),
                                    children=[
                                        html.H4("Filter"),
                                        html.Div(id="cost-base-year-text", style={"display": "none"}),
                                        html.Div(
                                            id="cost-compare-period-container",
                                            style={"display": "none"},
                                            children=[
                                                html.Label("Investitionsperiode"),
                                                dcc.Dropdown(
                                                    id="cost-compare-period-dropdown",
                                                    options=[],
                                                    value=None,
                                                    clearable=False,
                                                    disabled=True,
                                                ),
                                            ],
                                        ),
                                        period_filter_note("Einige Wirtschaftlichkeitsdiagramme zeigen bewusst alle Investitionsperioden. Der Periodenfilter wirkt daher nicht auf jede Darstellung."),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
                
                # Erzeugt den Dashboard-Tab für die Vergleichsvarianten und Sensitivität
                dcc.Tab(
                    id="tab-var",
                    label="Variantenvergleich / Sensitivität",
                    value="tab-var",
                    disabled=(len(file_options) < 2),
                    children=[
                        html.Div(style={"height": "12px"}),
                        html.Div(
                            style=FILTER_CONTENT_ROW_STYLE,
                            children=[
                                html.Div(
                                    style={"flex": "1", "minWidth": 0},
                                    children=[
                                        html.Div(id="var-overview-note", className="info-box"),
                                        register_agenda([
                                            ("var-section-systemkosten", "Systemkosten"),
                                            ("var-section-finanzkennzahlen", "Wirtschaftliche Differenzkennzahlen"),
                                            ("var-section-kostenvorteil", "Jährlicher Kostenvorteil / -nachteil"),
                                            ("var-section-leistungen", "Leistungen aller Komponenten"),
                                            ("var-section-speicher", "Kapazität der Speicherkomponenten"),
                                            ("var-section-stromlasten", "Gesamtstromlast und Reststromlast nach Erzeugung"),
                                            ("var-section-emissionen", "CO2-Emissionen"),
                                            ("var-section-vermeidungskosten", "CO2-Vermeidungskosten"),
                                        ]),
                                        html.Div(
                                            id="var-comparison-content",
                                            style={
                                                "display": "flex",
                                                "flexDirection": "column",
                                                "gap": "18px",
                                                "width": "100%",
                                                "boxSizing": "border-box",
                                            },
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className="filter-sidebar",
                                    style=filter_sidebar_style(True),
                                    children=[
                                        html.H4("Filter"),
                                        html.Div(
                                            id="var-year-filter",
                                            style={"display": "none", "marginBottom": "12px"},
                                            children=[
                                                html.Label("Investitionsperiode"),
                                                dcc.Dropdown(
                                                    id="var-year-dropdown",
                                                    options=[],
                                                    value=None,
                                                    clearable=False,
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            style={"marginBottom": "12px"},
                                            children=[
                                                html.Label("Anzahl Vergleichsvarianten"),
                                                dcc.Dropdown(
                                                    id="var-count-dropdown",
                                                    options=[{"label": f"{i} Vergleichsvarianten", "value": i} for i in range(1, 6)],
                                                    value=1,
                                                    clearable=False,
                                                ),
                                            ],
                                        ),
                                        html.Hr(),
                                        *[
                                            html.Div(
                                                id=f"var-slot-{i}-filter-wrapper",
                                                style={"display": "none", "marginBottom": "12px"},
                                                children=[
                                                    html.Label(f"Vergleich {i}: Vergleichsvariante"),
                                                    dcc.Dropdown(
                                                        id=f"var-slot-{i}-dropdown",
                                                        options=[],
                                                        value=None,
                                                        clearable=True,
                                                        placeholder="Variante wählen...",
                                                    ),
                                                ],
                                            )
                                            for i in range(1, 6)
                                        ],
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),

            ],
        ),
    ],
)


# %% Control Sync Callback (Dataset -> UI Defaults/Visibility)

@app.callback(
    Output("cap-year-dropdown", "options"),
    Output("cap-year-dropdown", "value"),
    Output("cap-year-filter", "style"),

    Output("ts-period-dropdown", "options"),
    Output("ts-period-dropdown", "value"),
    Output("ts-filter-container", "style"),

    Output("sankey-period-dropdown", "options"),
    Output("sankey-period-dropdown", "value"),
    Output("sankey-filter-container", "style"),

    Output("co2-period-dropdown", "options"),
    Output("co2-period-dropdown", "value"),

    Output("tab-exp", "disabled"),
    Output("tab-co2", "disabled"),
    Output("tab-cost", "disabled"),
    Output("tab-map", "disabled"),
    Output("tab-ops", "disabled"),

    Output("cap-sector-dropdown", "value"),
    Output("exp-sector-dropdown", "value"),

    Output("cost-base-year-text", "children"),
    Output("cost-compare-period-container", "style"),
    Output("cost-compare-period-dropdown", "options"),
    Output("cost-compare-period-dropdown", "value"),
    Output("cost-compare-period-dropdown", "disabled"),

    Output("main-tabs", "value"),
    Input("datafile-dropdown", "value"),
    State("main-tabs", "value"),
)
def sync_controls_for_dataset(nc_path, current_tab):
    """
    Dash-Callback: synchronisiert UI-Controls und Tab-Visibility nach Dataset-Wechsel
    (Jahresfilter, Periodenfilter, Tab enable/disable, Defaults)
    
    Inputs: nc_path: str (aus Dropdown)
            current_tab: aktueller Tab-Wert (State)

    Lädt State per get_dataset_state
    Konfiguriert Jahresfilter im Kapazitäten-Tab (MIP: Jahre, sonst hidden)
    Konfiguriert TS- und Sankey-Periodenfilter (nur sichtbar bei MIP)
    Aktiviert/Deaktiviert Ausbaupfad-Tab (nur MIP) und Kosten-Tab (wenn Kosten oder
    Investitionen vorhanden)                                                      
    Setzt Default-Sektoren
    Konfiguriert Kosten-Dropdown: Basisperiode und Vergleichsperioden
    Fallback: wenn aktueller Tab jetzt disabled ist, springt auf 'tab-cap'
    
    Outputs: Mehrere Dash-Outputs: Dropdown-Optionen/Values/Styles, Tab-Flags, Kostenfilter,
    nächster Tab
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei gewählt")

    # CAP-Year UI
    if st["has_mip"] and st["years"]:
        cap_year_options = [{"label": "Alle Perioden", "value": "all"}] + [
            {"label": str(y), "value": str(y)} for y in st["years"]
        ]
        cap_year_value = "all"
        cap_year_style = {"display": "block", "marginTop": "12px"}
    else:
        cap_year_options = [{"label": "Alle Perioden", "value": "all"}]
        cap_year_value = "all"
        cap_year_style = {"display": "none", "marginTop": "12px"}

    # TS UI
    ts_opts = st["ts_period_options"]
    ts_val = st["default_ts_period"]
    ts_style = filter_sidebar_style(st["has_mip"])

    # Sankey UI
    sank_opts = st["sank_period_options"]
    sank_val = st["default_sank_period"]
    sank_style = filter_sidebar_style(st["has_mip"])

    # CO2 UI
    co2_opts = [{"label": "Alle Perioden", "value": "all"}]
    co2_val = "all"

    # Tabs enabled/disabled
    exp_disabled = not st["has_mip"]
    co2_disabled = not bool(st.get("has_co2", False))
    ops_disabled = not bool(st.get("has_ops", False))
    cost_disabled = (
    ((st.get("df_total_cost") is None) or st["df_total_cost"].empty)
    and (st.get("df_inv_capex") is None or st["df_inv_capex"].empty)
    )
    map_disabled = (st.get("n") is None) or build_map_component_table(st.get("n")).empty

    # Default sectors
    cap_sector_val = st["default_sector"]
    exp_sector_val = st["default_sector"]

    # Cost filter configuration
    if (not cost_disabled) and st["has_mip_cost"] and st["years_cost"]:
        base_p = st["base_period"]
        compare_years = st["compare_years"]
        base_txt = ""
        compare_options = [{"label": str(y), "value": str(y)} for y in st["years_cost"]]
        compare_value = str(compare_years[0]) if compare_years else (str(base_p) if base_p is not None else str(st["years_cost"][0]))
        compare_disabled = False
        compare_style = {"display": "block"}
    elif not cost_disabled:
        base_txt = ""
        compare_style = {"display": "none"}
        compare_options = []
        compare_value = None
        compare_disabled = True
    else:
        base_txt = ""
        compare_style = {"display": "none"}
        compare_options = []
        compare_value = None
        compare_disabled = True

    # Tab fallback, falls aktueller Tab jetzt disabled ist
    next_tab = current_tab or "tab-cap"
    if next_tab == "tab-exp" and exp_disabled:
        next_tab = "tab-cap"
    if next_tab == "tab-co2" and co2_disabled:
        next_tab = "tab-cap"
    if next_tab == "tab-cost" and cost_disabled:
        next_tab = "tab-cap"
    if next_tab == "tab-map" and map_disabled:
        next_tab = "tab-cap"
    if next_tab == "tab-ops" and ops_disabled:
        next_tab = "tab-cap"

    return (
        cap_year_options, cap_year_value, cap_year_style,
        ts_opts, ts_val, ts_style,
        sank_opts, sank_val, sank_style,
        co2_opts, co2_val,
        exp_disabled, co2_disabled, cost_disabled, map_disabled, ops_disabled,
        cap_sector_val, exp_sector_val,
        base_txt, compare_style, compare_options, compare_value, compare_disabled,
        next_tab
    )


#%% Betriebsanalyse: Controls und Graphen

@app.callback(
    Output("ops-period-dropdown", "options"),
    Output("ops-period-dropdown", "value"),
    Input("datafile-dropdown", "value"),
)
def sync_ops_controls(nc_path):
    """
    Dash-Callback: synchronisiert Betriebsanalyse controls zwischen Datenbasis, Filtern und Anzeige.
    
    Inputs: nc_path.
    Outputs: synchronisierte Dropdownwerte, Optionen oder Layoutzustände.
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")
    opts = st.get("ops_period_options", [{"label": "Single", "value": "Single"}])
    value = st.get("default_ops_period", opts[0]["value"] if opts else "Single")
    return opts, value


@app.callback(
    Output("ops-autarky-graph", "figure"),
    Output("ops-load-metrics-table", "figure"),
    Output("ops-load-duration-graph", "figure"),
    Output("ops-pv-usage-graph", "figure"),
    Output("ops-technology-share-electric-graph", "figure"),
    Output("ops-technology-share-heat-graph", "figure"),
    Input("datafile-dropdown", "value"),
    Input("ops-period-dropdown", "value"),
)
def update_ops_tab(nc_path, period_value):
    """
    Dash-Callback: aktualisiert Betriebsanalyse tab anhand der aktuellen Nutzerauswahl.
    
    Inputs: nc_path, period_value.
    Outputs: aktualisierte Dash-Komponenten, Plotly-Abbildungen oder Layout-Elemente.
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")
    valid_periods = {str(o["value"]) for o in st.get("ops_period_options", [])}
    if period_value is None or str(period_value) not in valid_periods:
        period_value = st.get("default_ops_period", "Single")

    return finalize_figures(
        build_ops_autarky_fig(st.get("df_ops_autarky", pd.DataFrame()), period_value),
        build_ops_load_metrics_table_fig(st.get("df_ops_load_metrics", pd.DataFrame()), period_value),
        build_ops_load_duration_fig(st.get("n"), period_value),
        build_ops_pv_usage_fig(st.get("df_ops_pv_usage", pd.DataFrame())),
        build_ops_technology_share_fig(st.get("df_ops_technology_shares", pd.DataFrame()), "Strom"),
        build_ops_technology_share_fig(st.get("df_ops_technology_shares", pd.DataFrame()), "Wärme"),
    )


#%% Systemkarte: Controls

@app.callback(
    Output("map-component-dropdown", "options"),
    Output("map-component-dropdown", "value"),
    Output("map-period-dropdown", "options"),
    Output("map-period-dropdown", "value"),
    Output("map-period-container", "style"),
    Input("datafile-dropdown", "value"),
)
def sync_map_controls(nc_path):
    """
    Dash-Callback: Synchronisiert die Filter der Systemkarte mit der aktuell ausgewählten Datenbasis.
    
    Inputs: nc_path.
    Outputs: synchronisierte Dropdownwerte, Optionen oder Layoutzustände.
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")
    n = st.get("n")
    df_map = build_map_component_table(n) if n is not None else pd.DataFrame()

    component_options = build_map_component_options(df_map)

    if st.get("has_mip", False) and st.get("years", []):
        period_options = [{"label": "Alle Perioden", "value": "all"}] + [
            {"label": str(y), "value": str(y)} for y in st["years"]
        ]
        period_style = {"display": "block", "marginBottom": "12px"}
    else:
        period_options = [{"label": "Alle Perioden", "value": "all"}]
        period_style = {"display": "none", "marginBottom": "12px"}

    return component_options, [], period_options, "all", period_style


@app.callback(
    Output("network-map-graph", "srcDoc"),
    Input("datafile-dropdown", "value"),
    Input("map-component-dropdown", "value"),
    Input("map-period-dropdown", "value"),
)
def update_network_map(nc_path, selected_components, period_value):
    """
    Dash-Callback: Aktualisiert die Systemkarte im Dashboard, wenn sich Datenbasis, Komponentenfilter oder Periode ändern.
    
    Inputs: nc_path, selected_components, period_value.
    Outputs: HTML-Inhalt für die Systemkarte.
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")
    return build_network_map_html(
        st.get("n"),
        st.get("df_life", pd.DataFrame()),
        selected_components,
        period_value=period_value or "all",
    )

#%% Variantenvergleich: Sync (Dropdowns + Sichtbarkeit)

# Ein-/ausblenden von Filtern und Abshcnitten, Zuordnung der Sprungmarker und Anzahl der Vergleichsvarianten
VARIANT_SLOT_NUMBERS = list(range(1, 6))
VARIANT_FILTER_VISIBLE_STYLE = {"display": "block", "marginBottom": "12px"}
VARIANT_FILTER_HIDDEN_STYLE = {"display": "none", "marginBottom": "12px"}
VARIANT_SECTION_ANCHORS = {
    "Systemkosten": "var-section-systemkosten",
    "Wirtschaftliche Differenzkennzahlen": "var-section-finanzkennzahlen",
    "Jährlicher Kostenvorteil / -nachteil": "var-section-kostenvorteil",
    "Leistungen aller Komponenten": "var-section-leistungen",
    "Kapazität der Speicherkomponenten": "var-section-speicher",
    "Gesamtstromlast und Reststromlast nach Erzeugung": "var-section-stromlasten",
    "CO2-Emissionen": "var-section-emissionen",
    "CO2-Vermeidungskosten": "var-section-vermeidungskosten",
    "Hinweis": "var-section-hinweis",
}


def _normalise_variant_count(value) -> int:
    """
    Stellt sicher, dass die Anzahl der Vergleichsvarianten immer gültig ist.
    
    Inputs: value.
    Outputs: Gültige Ganzzahl zwischen 1 und 5.
    """
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 1
    return max(1, min(5, count))


def _variant_metric_card(title: str, fig: go.Figure, height: str) -> html.Div:
    """
    Erzeugt einen Diagrammabschnitt für den Variantenvergleich.

    Inputs: Abschnittstitel, Plotly-Abbildung und Diagrammhöhe.
    Outputs: Dash-HTML-Container für Diagramm oder Hinweistext.
    """
    fig = finalize_figure(fig)
    figure_title = _figure_title_text(fig)
    if is_empty_info_figure(fig):
        return html.Div(
            style={
                "borderTop": "1px solid #e5e5e5",
                "paddingTop": "10px",
            },
            children=[
                html.H4(title, style={"margin": "0 0 8px 0"}),
                html.Div(figure_title or "Für diese Auswertung liegen keine darstellbaren Daten vor.", className="info-box"),
            ],
        )
    return html.Div(
        style={
            "borderTop": "1px solid #e5e5e5",
            "paddingTop": "10px",
        },
        children=[
            html.H4(title, style={"margin": "0 0 8px 0"}),
            dcc.Graph(figure=fig, style={"height": height, "width": "100%"}),
        ],
    )


def _variant_message(text: str) -> html.Div:
    """
    Erstellt eine einfache Hinweisbox bzw. Meldung für den Variantenvergleich.
    
    Inputs: text.
    Outputs: Dash-Element mit formatiertem Hinweistext.
    """
    return html.Div(
        text,
        style={
            "color": "#666",
            "borderTop": "1px solid #e5e5e5",
            "paddingTop": "10px",
        },
    )


def _build_variant_cards(
    st_base: dict,
    base_name: str,
    cmp_path: str | None,
    period_cost: str,
    period_cap: str | None,
) -> list:
    """
    Erstellt alle Diagrammkarten für den Variantenvergleich (Vergleichsvariante gegenüber Basisvariante).
    
    Inputs: st_base, base_name, cmp_path, period_cost, period_cap.
    Outputs: Liste von Karten/Abschnitten für den Variantenvergleich.
    """
    if not cmp_path:
        return [("Hinweis", _variant_message("Bitte eine Vergleichsvariante wählen."))]

    st_cmp = get_dataset_state_fresh(cmp_path)
    cmp_name = _basename(cmp_path)
    if not st_cmp.get("ok", False):
        return [("Hinweis", _variant_message(f"{cmp_name} konnte nicht geladen werden."))]

    fig_cost = build_variant_total_cost_compare_fig(
        st_base=st_base,
        st_cmp=st_cmp,
        base_name=base_name,
        cmp_name=cmp_name,
        period_cost=period_cost,
    )
    financial_summary = build_variant_financial_summary(st_base, st_cmp)
    fig_fin = build_variant_financial_summary_fig(financial_summary)
    fig_cash = build_variant_delta_cashflow_fig(financial_summary.get("df_delta", pd.DataFrame()))
    fig_fin.update_layout(title=f"Wirtschaftliche Differenzkennzahlen: {cmp_name} gegenüber {base_name}")
    fig_cash.update_layout(title=f"Jährlicher Kostenvorteil / -nachteil: {cmp_name} gegenüber {base_name}")
    fig_cap = build_variant_capacity_compare_fig(
        st_base=st_base,
        st_cmp=st_cmp,
        base_name=base_name,
        cmp_name=cmp_name,
        period_value=period_cap,
        top_n=30,
    )
    fig_store = build_variant_storage_capacity_compare_fig(
        st_base=st_base,
        st_cmp=st_cmp,
        base_name=base_name,
        cmp_name=cmp_name,
        period_value=period_cap,
        top_n=30,
    )
    fig_load = build_variant_electric_load_compare_fig(
        st_base=st_base,
        st_cmp=st_cmp,
        base_name=base_name,
        cmp_name=cmp_name,
    )
    fig_emis = build_variant_emissions_compare_fig(
        st_base=st_base,
        st_cmp=st_cmp,
        base_name=base_name,
        cmp_name=cmp_name,
        period_value=period_cost,
    )
    fig_abatement = build_variant_abatement_cost_fig(
        st_base=st_base,
        st_cmp=st_cmp,
        base_name=base_name,
        cmp_name=cmp_name,
        period_value=period_cost,
    )

    return [
        ("Systemkosten", _variant_metric_card(f"Systemkosten: {cmp_name} gegenüber {base_name}", fig_cost, "360px")),
        ("Wirtschaftliche Differenzkennzahlen", _variant_metric_card(f"Wirtschaftliche Differenzkennzahlen: {cmp_name} gegenüber {base_name}", fig_fin, "500px")),
        ("Jährlicher Kostenvorteil / -nachteil", _variant_metric_card(f"Jährlicher Kostenvorteil / -nachteil: {cmp_name} gegenüber {base_name}", fig_cash, "430px")),
        ("Leistungen aller Komponenten", _variant_metric_card(f"Leistungen aller Komponenten: {cmp_name} gegenüber {base_name}", fig_cap, "440px")),
        ("Kapazität der Speicherkomponenten", _variant_metric_card(f"Kapazität der Speicherkomponenten: {cmp_name} gegenüber {base_name}", fig_store, "440px")),
        ("Gesamtstromlast und Reststromlast nach Erzeugung", _variant_metric_card(f"Gesamtstromlast und Reststromlast nach Erzeugung: {cmp_name} gegenüber {base_name}", fig_load, "440px")),
        ("CO2-Emissionen", _variant_metric_card(f"CO2-Emissionen: {cmp_name} gegenüber {base_name}", fig_emis, "360px")),
        ("CO2-Vermeidungskosten", _variant_metric_card(f"CO2-Vermeidungskosten: {cmp_name} gegenüber {base_name}", fig_abatement, "300px")),
    ]


@app.callback(
    [
        Output("var-year-dropdown", "options"),
        Output("var-year-dropdown", "value"),
        Output("var-year-filter", "style"),
        Output("tab-var", "disabled"),
    ]
    + [
        out
        for i in VARIANT_SLOT_NUMBERS
        for out in (
            Output(f"var-slot-{i}-dropdown", "options"),
            Output(f"var-slot-{i}-dropdown", "value"),
            Output(f"var-slot-{i}-filter-wrapper", "style"),
        )
    ],
    Input("datafile-dropdown", "value"),
    Input("var-count-dropdown", "value"),
    State("var-year-dropdown", "value"),
    *[State(f"var-slot-{i}-dropdown", "value") for i in VARIANT_SLOT_NUMBERS],
)
def sync_variant_compare_controls(base_path, count_value, current_year, *current_cmp_paths):
    """
    Synchronisiert Vergleichsblöcke, Jahresfilter und Tab-Sichtbarkeit.

    Inputs: Datenbasis, Anzahl der Vergleichsvarianten, aktuelles Jahr und aktuelle Variantenpfade.
    Outputs: Dropdownoptionen, Werte, Sichtbarkeitszustände und Tab-Aktivierung.
    """
    count = _normalise_variant_count(count_value)
    hidden_slots = [
        ([], None, VARIANT_FILTER_HIDDEN_STYLE.copy())
        for _ in VARIANT_SLOT_NUMBERS
    ]

    if len(file_options) < 2 or base_path is None:
        return [[], None, {"display": "none"}, True] + [item for slot in hidden_slots for item in slot]

    opts = [o for o in file_options if o.get("value") != base_path]
    valid_values = {o["value"] for o in opts}
    current_values = [
        path if path in valid_values else None
        for path in current_cmp_paths
    ]

    st_base = get_dataset_state_fresh(base_path) if base_path else _empty_state("keine Datei")

    if st_base.get("has_mip", False) and st_base.get("years", []):
        years = st_base["years"]
        year_opts = [{"label": str(y), "value": str(y)} for y in years]
        years_set = {str(y) for y in years}
        y_val = current_year if (current_year in years_set) else str(min(years))
        year_style = {"display": "block", "minWidth": "220px"}
    else:
        year_opts = []
        y_val = None
        year_style = {"display": "none"}

    slot_outputs = []
    for idx, path in enumerate(current_values, start=1):
        visible = idx <= count
        filter_style = VARIANT_FILTER_VISIBLE_STYLE.copy() if visible else VARIANT_FILTER_HIDDEN_STYLE.copy()
        value = path if visible else None
        if visible and value is None and opts:
            value = opts[idx - 1]["value"] if idx <= len(opts) else None
        slot_outputs.extend([opts, value, filter_style])

    return [year_opts, y_val, year_style, False] + slot_outputs


@app.callback(
    Output("var-overview-note", "children"),
    Input("datafile-dropdown", "value"),
)
def update_variant_overview_note(base_path):
    """
    Zeigt die Bezugslogik des Variantenvergleichs direkt oberhalb der Auswertungen.

    Inputs: Pfad der ausgewählten Datenbasis.
    Outputs: Dash-Hinweiscontainer mit Bezugs- und Filterlogik.
    """
    if not base_path:
        return "Bitte oben rechts eine Datenbasis auswählen. Alle Vergleichsvarianten werden anschließend gegen diese Datenbasis ausgewertet."
    return (
        f"Alle folgenden Variantenvergleiche beziehen sich auf die oben rechts ausgewählte Datenbasis "
        f"„{_basename(base_path)}“. Jede gewählte Vergleichsvariante wird direkt mit dieser Datenbasis verglichen. "
        "Einige technische Diagramme zeigen bewusst alle Investitionsperioden; der Periodenfilter wirkt daher nicht auf jede Darstellung."
    )

#%% Graph Callbacks (alle dataset-basiert)

@app.callback(
    Output("cap-power-graph", "figure"),
    Output("cap-energy-graph", "figure"),
    Input("datafile-dropdown", "value"),
    Input("cap-sector-dropdown", "value"),
    Input("cap-year-dropdown", "value"),
)
def update_cap_graphs(nc_path, sector, selected_period):
    """
    Dash-Callback: aktualisiert Nennleistungs- und Speicherkapazitäts-Balkendiagramme für
    einen gewählten Sektor und eine Investitionsperiode oder alle Perioden
    
    Inputs: nc_path: str
            sector: str
            selected_period: str
    
    Lädt State
    Validiert selected_period gegen erlaubte Perioden; fallback: alle Perioden
    Filtert df_sector_p/e nach Jahren via _filter_df_sector_years
    Erzeugt Figuren via build_sector_bar (mit subcarrier_color_map)
    
    Outputs: aktualisierte (fig_p, fig_e): go.Figure, go.Figure    
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")
    if st["has_mip"] and st["years"]:
        allowed = {str(y) for y in st["years"]}
        if selected_period in (None, "", "all"):
            selected_years = [str(y) for y in st["years"]]  # fallback: alle
        elif str(selected_period) in allowed:
            selected_years = [str(selected_period)]
        else:
            selected_years = [str(y) for y in st["years"]]
    else:
        selected_years = ["Single"]


    if sector not in SECTORS:
        sector = st["default_sector"]

    dfp = st["by_sector_p"].get(sector)
    dfe = st["by_sector_e"].get(sector)

    dfp_f, years_f = _filter_df_sector_years(dfp, selected_years, st["years"])
    dfe_f, _ = _filter_df_sector_years(dfe, selected_years, st["years"])

    fig_p = build_sector_bar(dfp_f, sector, years_f, value_col="p_nom", unit="kW", title_prefix="Nennleistungen",
                             color_map=st["subcarrier_color_map"])
    fig_e = build_sector_bar(dfe_f, sector, years_f, value_col="e_nom", unit="kWh", title_prefix="Speicherkapazität",
                             color_map=st["subcarrier_color_map"])
    return finalize_figures(fig_p, fig_e)


@app.callback(
    Output("ts-strom-graph", "figure"),
    Output("ts-waerme-graph", "figure"),
    Output("ts-sonst-graph", "figure"),
    Input("datafile-dropdown", "value"),
    Input("ts-period-dropdown", "value"),
)
def update_timeseries_by_period(nc_path, period_value):
    """
    Dash-Callback: aktualisiert Zeitreihen-Plots für Strom / Wärme / Sonstige für eine gewählte
    Investitionsperiode
    
    Inputs: nc_path: str
            period_value: str
    
    Lädt State und validiert period_value gegen ts_period_options
    Filtert df_dyn_all auf period_value (falls vorhanden)
    Bei MIP: filtert meta auf aktive Assets in der Periode
    Erzeugt drei Figuren via build_sector_timeseries_fig (mit timeseries_color_map)
    
    Outputs: aktualisierte Strom-, Wärme- und Sonst-Figuren.
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")

    # period_value validieren (bei Dataset-Wechsel kann ein alter Wert hängen bleiben)
    valid_periods = {o["value"] for o in st.get("ts_period_options", [])}
    if (period_value is None) or (str(period_value) not in {str(v) for v in valid_periods}):
        period_value = st.get("default_ts_period", "Single")

    df = st["df_dyn_all"].copy()
    if "period" in df.columns and period_value is not None:
        df = df[df["period"].astype(str) == str(period_value)]

    if st["has_mip"]:
        active_set = active_assets_in_period(st["df_life"], period_value)
        meta_active = filter_meta_to_active(st["meta_ts"], active_set, st["df_life"])
    else:
        meta_active = st["meta_ts"]

    fig_s = build_sector_timeseries_fig(df, meta_active, "Strom", unit="kW", max_traces=30,
                                        ts_color_map=st["timeseries_color_map"])
    fig_w = build_sector_timeseries_fig(df, meta_active, "Wärme", unit="kW", max_traces=30,
                                        ts_color_map=st["timeseries_color_map"])
    fig_o = build_sector_timeseries_fig(df, meta_active, "Sonstige", unit="kW", max_traces=30,
                                        ts_color_map=st["timeseries_color_map"])
    return finalize_figures(fig_s, fig_w, fig_o)


@app.callback(
    Output("exp-path-graph", "figure"),
    Output("exp-life-graph", "figure"),
    Input("datafile-dropdown", "value"),
    Input("exp-sector-dropdown", "value"),
)
def update_expansion_tab(nc_path, sector):
    """
    Dash-Callback: aktualisiert Ausbaupfad- und Lifetime-Plots für einen gewählten Sektor 
    (nur MIP)
    
    Inputs: nc_path: str
            sector: str
            
    Lädt State, validiert Sektor
    Wenn kein MIP: gibt Platzhalter-Figuren zurück
    Sonst: build_expansion_path_scatter + build_lifetime_timeline_fig

    Outputs: aktualisierte (fig_exp, fig_life): go.Figure      
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")

    if sector not in SECTORS:
        sector = st["default_sector"]

    if not st["has_mip"]:
        fig_exp = go.Figure().update_layout(title="Ausbaupfad (nur bei MIP verfügbar)")
        fig_life = go.Figure().update_layout(title="Lebensdauer (nur bei MIP verfügbar)")
        return finalize_figures(fig_exp, fig_life)

    fig_exp = build_expansion_path_scatter(
        st["by_sector_p"],
        sector,
        st["years"],
        value_col="p_nom",
        unit="kW",
        max_series=25,
        color_map=st["subcarrier_color_map"],
    )

    fig_life = build_lifetime_timeline_fig(st["df_life"], sector, color_map=st["subcarrier_color_map"])
    return finalize_figures(fig_exp, fig_life)


@app.callback(
    Output("sankey-graph", "figure"),
    Input("datafile-dropdown", "value"),
    Input("sankey-period-dropdown", "value"),
)
def update_sankey(nc_path, period_value):
    """
    Dash-Callback: aktualisiert das Sankey-Diagramm für eine gewählte Periode (bei MIP) bzw
    für alle Snapshots (Single-year)
    
    Inputs: nc_path: str
            period_value: str
            
    Lädt State und validiert period_value gegen sank_period_options
    Wenn kein Netzwerk geladen: gibt Platzhalter zurück
    Wenn MIP: ruft build_sankey_fig mit period_value und Farbinfos auf
    Sonst: ruft build_sankey_fig ohne Periodenfilter auf
    
    Outputs: aktualisiertes Sankey-Diagramm, go.figure
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")
    
    valid = {o["value"] for o in st.get("sank_period_options", [])}
    if (period_value is None) or (str(period_value) not in {str(v) for v in valid}):
        period_value = st.get("default_sank_period", "Single")

    if not st["ok"] or st["n"] is None:
        return finalize_figure(go.Figure().update_layout(title="Sankey (keine Datenbasis)"))

    if st["has_mip"]:
        return finalize_figure(build_sankey_fig(st["n"], 
                                df_life=st["df_life"], 
                                period_value=period_value, 
                                max_links=None, 
                                value_unit="kWh",
                                meta_ts=st["meta_ts"],
                                ts_color_map=st["timeseries_color_map"],
                                ))
    
    return finalize_figure(build_sankey_fig(
        st["n"],
        df_life=st["df_life"],
        period_value=None,
        max_links=None,
        value_unit="kWh",
        meta_ts=st["meta_ts"],                           
        ts_color_map=st["timeseries_color_map"],
    ))

@app.callback(
    Output("co2-period-totals-graph", "figure"),
    Output("co2-cost-totals-graph", "figure"),
    Output("co2-intensity-graph", "figure"),
    Input("datafile-dropdown", "value"),
)
def update_co2_tab(nc_path):
    """
    Dash-Callback: aktualisiert den kompletten CO2-Tab im Dashboard

    Inputs: Pfad der ausgewählten Datenbasis.
    Outputs: drei Plotly-Abbildungen für Emissionen, CO2-Kosten und CO2-Intensitäten.
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")
    period_value = "all"

    df_emissions = st.get("df_emissions", pd.DataFrame())
    df_intensity = st.get("df_co2_intensity", pd.DataFrame())

    fig_emis = build_co2_period_scope_stack_fig(
        df_emissions,
        st["years"],
        value_col="emissions_t",
        unit="t CO2/a",
        title="CO2-Emissionen nach Scope je Investitionsperiode (Jahreswert)",
        period_value=period_value,
    )
    fig_cost = build_co2_period_scope_stack_fig(
        df_emissions,
        st["years"],
        value_col="co2_cost_eur",
        unit="EUR/a",
        title="CO2-Kosten nach Scope je Investitionsperiode (Jahreswert)",
        period_value=period_value,
    )
    fig_int = build_co2_intensity_scope_fig(df_intensity, st["years"], period_value=period_value)
    return finalize_figures(fig_emis, fig_cost, fig_int)

@app.callback(
    Output("cost-period-totals-graph", "figure"),
    Output("cost-investment-capex-graph", "figure"),
    Output("cost-lcoe-tech-graph", "figure"),
    Output("cost-heat-tech-graph", "figure"),
    Output("cost-lcos-graph", "figure"),
    Output("cost-cashflow-graph", "figure"),
    Output("cost-composition-graph", "figure"),
    Output("cost-total-pie-graph", "figure"),
    Input("datafile-dropdown", "value"),
    Input("cost-compare-period-dropdown", "value"),
)

def update_cost_tab(nc_path, selected_period):
    """
    Dash-Callback: aktualisiert die Kostenplots für die gewählte Investitionsperiode
    
    Inputs: nc_path: str
            selected_period: str|None
            
    Lädt den Dataset-State und baut die aktuellen Kosten-, Investitions-, LCOE/LCOH-,
    LCOS- und Cashflow-Diagramme.
    
    Outputs: Aktualisierte Kostenfiguren.
    """
    st = get_dataset_state_fresh(nc_path) if nc_path else _empty_state("keine Datei")

    df_inv = st.get("df_inv_capex")
    horizon_end = _analysis_horizon_end_year(st.get("df_life", pd.DataFrame()), st["years_cost"])
    fig_inv = build_investment_capex_totals_fig(df_inv, st["years_cost"], horizon_end) if st.get("has_mip", False) else \
              build_investment_capex_totals_fig(df_inv, [])

    df_total_cost = st.get("df_total_cost", pd.DataFrame())
    df_lcoe = st.get("df_lcoe", pd.DataFrame())
    df_lcos = st.get("df_lcos", pd.DataFrame())
    df_cashflow = st.get("df_cashflow", pd.DataFrame())
    if df_total_cost is None or df_total_cost.empty:
        f1 = go.Figure().update_layout(title="Gesamtkosten (keine Daten)")
        f2 = go.Figure().update_layout(title="Stromgestehungskosten (LCOE) je Technologie (keine Daten)")
        f3 = go.Figure().update_layout(title="Wärmegestehungskosten (LCOH) je Technologie (keine Daten)")
        f4 = go.Figure().update_layout(title="Spezifische Speicherkosten (LCOS) (keine Daten)")
        f5 = go.Figure().update_layout(title="Cashflow-Darstellung pro Jahr (keine Daten)")
        f6 = go.Figure().update_layout(title="Gesamtkostenverteilung (keine Daten)")
        f7 = go.Figure().update_layout(title="Gesamtkostenstruktur nach Kostenart (keine Daten)")
        return finalize_figures(f1, fig_inv, f2, f3, f4, f5, f6, f7)

    if st["has_mip_cost"]:
        valid_periods = {str(y) for y in st["years_cost"]}
        if selected_period is None or str(selected_period) not in valid_periods:
            selected_period = str(st["base_period"] or st["years_cost"][0])
        else:
            selected_period = str(selected_period)

        fig_tot = build_total_cost_period_fig(df_total_cost, st["years_cost"])
        fig_lcoe_tech = build_lcoe_technology_fig(df_lcoe, "Alle", max_components=30, years=st["years_cost"])
        fig_heat_tech = build_heat_generation_cost_fig(df_lcoe, "Alle", max_components=30, years=st["years_cost"])
        fig_lcos = build_specific_storage_cost_fig(df_lcos, st["years_cost"], "Alle")
        fig_cashflow = build_cashflow_fig(df_cashflow)
        base_period = str(st["base_period"] or st["years_cost"][0])
        fig_comp = build_total_cost_comparison_fig(df_total_cost, base_period, selected_period, max_components=30)
        fig_pie = build_total_cost_type_pie_fig(df_total_cost, df_inv, st["years_cost"], selected_period, df_cashflow=df_cashflow)
        return finalize_figures(fig_tot, fig_inv, fig_lcoe_tech, fig_heat_tech, fig_lcos, fig_cashflow, fig_comp, fig_pie)

    # Single-year
    single_period = "Single"
    fig_tot = build_total_cost_singleyear_fig(df_total_cost, single_period)
    df_single = df_total_cost[df_total_cost["period"].astype(str) == single_period].copy()
    fig_lcoe_tech = build_lcoe_technology_fig(df_lcoe, single_period, max_components=30)
    fig_heat_tech = build_heat_generation_cost_fig(df_lcoe, single_period, max_components=30)
    fig_lcos = build_specific_storage_cost_fig(df_lcos, [], single_period)
    fig_cashflow = build_cashflow_fig(df_cashflow)
    fig_comp = build_total_cost_component_fig(df_single, max_components=30)
    fig_pie = build_total_cost_type_pie_fig(df_total_cost, df_inv, [], single_period, df_cashflow=df_cashflow)
    return finalize_figures(fig_tot, fig_inv, fig_lcoe_tech, fig_heat_tech, fig_lcos, fig_cashflow, fig_comp, fig_pie)

@app.callback(
    Output("var-comparison-content", "children"),
    Input("datafile-dropdown", "value"),
    Input("var-count-dropdown", "value"),
    Input("var-year-dropdown", "value"),
    *[Input(f"var-slot-{i}-dropdown", "value") for i in VARIANT_SLOT_NUMBERS],
)
def update_variant_compare_tab(base_path, count_value, year_value, *cmp_paths):
    """
    Erstellt die Inhalte der Vergleichsvarianten gruppiert nach Auswertungstyp.

    Inputs: Datenbasis, Anzahl der Vergleichsvarianten, Periodenwahl und Variantenpfade.
    Outputs: Dash-HTML-Elemente für den Variantenvergleich.
    """
    count = _normalise_variant_count(count_value)
    if base_path is None:
        return []

    st_base = get_dataset_state_fresh(base_path) if base_path else _empty_state("keine Datei")
    if not st_base.get("ok", False):
        return []

    base_name = _basename(base_path)
    if st_base.get("has_mip", False) and st_base.get("years", []):
        period_cost = str(year_value) if year_value is not None else str(min(st_base["years"]))
        period_cap = period_cost
    else:
        period_cost = "Single"
        period_cap = None

    grouped_cards: dict[str, list] = {}
    section_order: list[str] = []
    used_paths = set()
    for idx, cmp_path in enumerate(cmp_paths, start=1):
        if idx > count:
            continue
        if cmp_path == base_path:
            section = "Hinweis"
            grouped_cards.setdefault(section, []).append(
                _variant_message("Die Datenbasis kann nicht als Vergleichsvariante gewählt werden.")
            )
            if section not in section_order:
                section_order.append(section)
            continue
        if cmp_path in used_paths:
            section = "Hinweis"
            grouped_cards.setdefault(section, []).append(
                _variant_message("Diese Vergleichsvariante ist bereits in einer anderen Spalte ausgewählt.")
            )
            if section not in section_order:
                section_order.append(section)
            continue
        if cmp_path:
            used_paths.add(cmp_path)
        for section, card in _build_variant_cards(st_base, base_name, cmp_path, period_cost, period_cap):
            grouped_cards.setdefault(section, []).append(card)
            if section not in section_order:
                section_order.append(section)

    children = []
    for section in section_order:
        cards = grouped_cards.get(section, [])
        if not cards:
            continue
        children.append(
            html.Div(
                id=VARIANT_SECTION_ANCHORS.get(section, f"var-section-{len(children) + 1}"),
                className="scroll-anchor",
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "12px",
                    "borderTop": "1px solid #d8dee6",
                    "paddingTop": "12px",
                },
                children=[
                    html.H3(section, style={"margin": "0 0 4px 0"}),
                    *cards,
                ],
            )
        )
    return children

#%% RUN

if __name__ == "__main__":
    if not file_options:
        print(f"[WARN] Keine .nc-Dateien in DATA_DIR gefunden: {DATA_DIR}")
    app.run(debug=False, use_reloader=False, threaded=False)
