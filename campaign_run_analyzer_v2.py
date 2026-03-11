#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""campaign_run_analyzer_v2.py

Standalone CLI analyzer for F5 AI Security "Get campaign run" response export.

Input: local JSON file (full response of /backend/v1/campaign-runs/{campaignRunId})
Output: one HTML report.

Rules:
- Only direct statistics based on fields present in the response schema.
- Vulnerability rate = vulnerable_count / total_count.
- ARSScore is displayed ONLY if present in response (no inference).
- Designed for large JSON: uses ijson streaming if installed.

Enhancement v2:
- In addition to results.converter (result-level), also analyze attack.converters[][]
  (attack configuration-level converters), including coverage, vulnerability rate,
  and vector+attack-converter combinations.

Dependencies:
- jinja2 (required)
- ijson (optional, recommended for very large JSON)

"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except Exception:
    print("ERROR: Missing dependency 'jinja2'. Install with: pip install jinja2", file=sys.stderr)
    raise

# Optional streaming parser
try:
    import ijson  # type: ignore
    _HAS_IJSON = True
except Exception:
    _HAS_IJSON = False


# -----------------------------
# Helpers
# -----------------------------

def _as_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return int(x)
        if isinstance(x, (int,)):
            return int(x)
        if isinstance(x, float):
            return int(x)
        s = str(x).strip()
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default


def _as_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        if isinstance(x, bool):
            return float(int(x))
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default


def _pct(num: int, den: int) -> float:
    return (num / den) if den else 0.0


def _fmt_pct(p: float) -> str:
    return f"{p*100:.2f}%"


def _fmt_num(x: Any) -> str:
    if x is None:
        return "N/A"
    if isinstance(x, int):
        return f"{x:,}"
    if isinstance(x, float):
        if math.isfinite(x):
            return f"{x:.4g}"
        return "N/A"
    return str(x)


def _iso_to_local(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    try:
        ss = s.replace('Z', '+00:00')
        dt = _dt.datetime.fromisoformat(ss)
        return dt.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception:
        return s


def _build_rate_table(stats: Dict[str, Dict[str, int]], sort_desc: bool = True) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for k, v in stats.items():
        total = v.get('total', 0)
        vuln = v.get('vuln', 0)
        rows.append({'name': k, 'total': total, 'vulnerable': vuln, 'rate': _pct(vuln, total)})
    rows.sort(key=lambda r: (r['rate'], r['total']), reverse=sort_desc)
    return rows


def _top_n_by_rate(stats: Dict[str, Dict[str, int]], n: int = 10, min_total: int = 1) -> List[Tuple[str, int, int, float]]:
    rows: List[Tuple[str, int, int, float]] = []
    for k, v in stats.items():
        total = v.get('total', 0)
        vuln = v.get('vuln', 0)
        if total >= min_total:
            rows.append((k, total, vuln, _pct(vuln, total)))
    rows.sort(key=lambda x: (x[3], x[1]), reverse=True)
    return rows[:n]


# -----------------------------
# Core analysis
# -----------------------------

@dataclass
class MetaInfo:
    run_id: str = ""
    run_name: str = ""
    campaign: str = ""
    status: str = ""
    created_at: Optional[str] = None
    start_at: Optional[str] = None
    created_by: str = ""

    CASIScore: Optional[float] = None
    ARSScore: Optional[float] = None
    casiScorePositionDelta: Optional[float] = None
    costOfSecurity: Optional[float] = None
    rtpRatio: Optional[float] = None
    averagePerformance: Optional[float] = None

    total_field: Optional[int] = None
    actionsCount: Optional[int] = None
    progress: Optional[int] = None


class Analyzer:
    def __init__(self):
        self.total_tests = 0
        self.total_vulnerable = 0
        self.total_errors = 0

        self.by_vector = defaultdict(lambda: {'total': 0, 'vuln': 0})
        self.by_pack = defaultdict(lambda: {'total': 0, 'vuln': 0})
        self.by_provider = defaultdict(lambda: {'total': 0, 'vuln': 0, 'errors': 0})
        self.by_technique = defaultdict(lambda: {'total': 0, 'vuln': 0})

        # Converter stats
        self.by_converter = defaultdict(lambda: {'total': 0, 'vuln': 0})              # result-level results.converter
        self.by_attack_converter = defaultdict(lambda: {'total': 0, 'vuln': 0})       # attack-level attack.converters[][] (flattened)

        self.by_intent_cat = defaultdict(lambda: {'total': 0, 'vuln': 0})
        self.by_severity = defaultdict(lambda: {'total': 0, 'vuln': 0})
        self.by_steps = defaultdict(lambda: {'total': 0, 'vuln': 0})

        # joint keys
        self.provider_vector = defaultdict(lambda: {'total': 0, 'vuln': 0})           # provider||vector
        self.vector_converter = defaultdict(lambda: {'total': 0, 'vuln': 0})          # vector||results.converter
        self.vector_attack_converter = defaultdict(lambda: {'total': 0, 'vuln': 0})   # vector||attack.converter

        self.coverage = {
            'vectors': set(),
            'packs': set(),
            'providers': set(),
            'techniques': set(),
            'converters': set(),          # result-level
            'attack_converters': set(),   # attack-level
            'intentCategories': set(),
            'severities': set(),
            'steps': set(),
        }

        self.unknown_values = Counter()
        self.error_summaries = Counter()
        self.result_error_types = Counter()

    def _norm(self, x: Any, label: str) -> str:
        if x is None or x == "":
            self.unknown_values[f"{label}:<missing>"] += 1
            return "unknown"
        s = str(x)
        if s.strip() == "":
            self.unknown_values[f"{label}:<blank>"] += 1
            return "unknown"
        return s

    @staticmethod
    def _flatten_attack_converters(raw: Any) -> List[str]:
        """Flatten attack.converters which is typically converters[][].

        We accept:
        - list[list[str]] (expected)
        - list[str] (tolerated)
        - others -> empty
        """
        out: List[str] = []
        if isinstance(raw, list):
            for chain in raw:
                if isinstance(chain, list):
                    for c in chain:
                        if c is None:
                            continue
                        out.append(str(c))
                elif chain is not None:
                    out.append(str(chain))
        return out

    def consume_attack_run(self, attack_run: Dict[str, Any]):
        provider = self._norm(attack_run.get('providerName'), 'providerName')
        self.coverage['providers'].add(provider)

        self.by_provider[provider]['errors'] += _as_int(attack_run.get('errorCount'), 0)
        self.total_errors += _as_int(attack_run.get('errorCount'), 0)

        attack = attack_run.get('attack') or {}
        vector = self._norm(attack.get('vector'), 'attack.vector')
        pack = self._norm(attack.get('pack'), 'attack.pack')
        technique = self._norm(attack.get('technique'), 'attack.technique')

        self.coverage['vectors'].add(vector)
        self.coverage['packs'].add(pack)
        self.coverage['techniques'].add(technique)

        # attack-level converters (flatten + unique per attackRun)
        raw_attack_converters = attack.get('converters')
        flat_attack_converters = [self._norm(c, 'attack.converters') for c in self._flatten_attack_converters(raw_attack_converters)]
        attack_converters_unique = sorted(set(flat_attack_converters))
        for c in attack_converters_unique:
            self.coverage['attack_converters'].add(c)

        results = attack_run.get('results') or []
        if not isinstance(results, list):
            self.unknown_values['results:<non_list>'] += 1
            return

        for r in results:
            if not isinstance(r, dict):
                self.unknown_values['result_item:<non_dict>'] += 1
                continue

            vuln = bool(r.get('vulnerable', False))
            self.total_tests += 1
            if vuln:
                self.total_vulnerable += 1

            # update attack dimensions
            self.by_vector[vector]['total'] += 1
            self.by_pack[pack]['total'] += 1
            self.by_provider[provider]['total'] += 1
            self.by_technique[technique]['total'] += 1
            if vuln:
                self.by_vector[vector]['vuln'] += 1
                self.by_pack[pack]['vuln'] += 1
                self.by_provider[provider]['vuln'] += 1
                self.by_technique[technique]['vuln'] += 1

            # converter (result-level)
            converter = self._norm(r.get('converter'), 'results.converter')
            self.coverage['converters'].add(converter)
            self.by_converter[converter]['total'] += 1
            if vuln:
                self.by_converter[converter]['vuln'] += 1

            # converter (attack-level): attribute this result to all converters configured for this attackRun
            for ac in attack_converters_unique:
                self.by_attack_converter[ac]['total'] += 1
                if vuln:
                    self.by_attack_converter[ac]['vuln'] += 1

            # intent category
            intent_cat = self._norm(r.get('intentCategory'), 'results.intentCategory')
            self.coverage['intentCategories'].add(intent_cat)
            self.by_intent_cat[intent_cat]['total'] += 1
            if vuln:
                self.by_intent_cat[intent_cat]['vuln'] += 1

            # severity
            sev = self._norm(r.get('severity'), 'results.severity')
            self.coverage['severities'].add(sev)
            self.by_severity[sev]['total'] += 1
            if vuln:
                self.by_severity[sev]['vuln'] += 1

            # conversation steps
            steps = r.get('conversationSteps')
            steps_key = str(_as_int(steps, -1)) if steps is not None else 'unknown'
            if steps_key == '-1':
                steps_key = 'unknown'
                self.unknown_values['conversationSteps:<missing>'] += 1
            self.coverage['steps'].add(steps_key)
            self.by_steps[steps_key]['total'] += 1
            if vuln:
                self.by_steps[steps_key]['vuln'] += 1

            # joint stats
            pv_key = f"{provider}||{vector}"
            self.provider_vector[pv_key]['total'] += 1
            if vuln:
                self.provider_vector[pv_key]['vuln'] += 1

            vc_key = f"{vector}||{converter}"
            self.vector_converter[vc_key]['total'] += 1
            if vuln:
                self.vector_converter[vc_key]['vuln'] += 1

            for ac in attack_converters_unique:
                vac_key = f"{vector}||{ac}"
                self.vector_attack_converter[vac_key]['total'] += 1
                if vuln:
                    self.vector_attack_converter[vac_key]['vuln'] += 1

            # errors
            err = r.get('error')
            err_sum = r.get('errorSummary')
            if err:
                self.result_error_types[self._norm(err, 'results.error')] += 1
            if err_sum:
                self.error_summaries[self._norm(err_sum, 'results.errorSummary')] += 1

    def finalize(self) -> Dict[str, Any]:
        overall_rate = _pct(self.total_vulnerable, self.total_tests)

        provider_list = sorted(self.coverage['providers'])
        vector_list = sorted(self.coverage['vectors'])

        matrix = []
        for p in provider_list:
            row = {'provider': p, 'cells': []}
            for v in vector_list:
                key = f"{p}||{v}"
                st = self.provider_vector.get(key, {'total': 0, 'vuln': 0})
                total = st.get('total', 0)
                vuln = st.get('vuln', 0)
                row['cells'].append({'vector': v, 'total': total, 'vulnerable': vuln, 'rate': _pct(vuln, total)})
            matrix.append(row)

        # vector+result.converter combos
        combo_rows = []
        for k, st in self.vector_converter.items():
            total = st['total']
            vuln = st['vuln']
            if total == 0:
                continue
            v, c = k.split('||', 1)
            combo_rows.append({'vector': v, 'converter': c, 'total': total, 'vulnerable': vuln, 'rate': _pct(vuln, total)})
        combo_rows.sort(key=lambda r: (r['rate'], r['total']), reverse=True)

        # vector+attack.converter combos
        combo_rows_attack = []
        for k, st in self.vector_attack_converter.items():
            total = st['total']
            vuln = st['vuln']
            if total == 0:
                continue
            v, c = k.split('||', 1)
            combo_rows_attack.append({'vector': v, 'converter': c, 'total': total, 'vulnerable': vuln, 'rate': _pct(vuln, total)})
        combo_rows_attack.sort(key=lambda r: (r['rate'], r['total']), reverse=True)

        # critical severity stats
        critical_vuln = 0
        critical_total = 0
        for sev, st in self.by_severity.items():
            if str(sev).lower() == 'critical':
                critical_total += st['total']
                critical_vuln += st['vuln']

        return {
            'overall': {
                'total_tests': self.total_tests,
                'total_vulnerable': self.total_vulnerable,
                'vulnerability_rate': overall_rate,
                'total_errors': self.total_errors,
                'critical_total': critical_total,
                'critical_vulnerable': critical_vuln,
                'critical_vulnerability_rate': _pct(critical_vuln, critical_total),
            },
            'coverage': {
                'vectors': len(self.coverage['vectors']),
                'packs': len(self.coverage['packs']),
                'providers': len(self.coverage['providers']),
                'techniques': len(self.coverage['techniques']),
                'converters': len(self.coverage['converters']),
                'attack_converters': len(self.coverage['attack_converters']),
                'intentCategories': len(self.coverage['intentCategories']),
                'severities': len(self.coverage['severities']),
                'steps': len(self.coverage['steps']),
                'vector_list': vector_list,
                'provider_list': provider_list,
            },
            'tables': {
                'by_vector': _build_rate_table(self.by_vector),
                'by_pack': _build_rate_table(self.by_pack),
                'by_provider': _build_rate_table({k: {'total': v['total'], 'vuln': v['vuln']} for k, v in self.by_provider.items()}),
                'by_converter': _build_rate_table(self.by_converter),
                'by_attack_converter': _build_rate_table(self.by_attack_converter),
                'by_intent_cat': _build_rate_table(self.by_intent_cat),
                'by_severity': _build_rate_table(self.by_severity, sort_desc=False),
                'by_technique': _build_rate_table(self.by_technique),
                'by_steps': _build_rate_table(self.by_steps, sort_desc=False),
            },
            'matrix': {
                'provider_vector': matrix,
            },
            'top': {
                'vector_top10': _top_n_by_rate(self.by_vector, 10, min_total=1),
                'pack_top10': _top_n_by_rate(self.by_pack, 10, min_total=1),
                'provider_top10': _top_n_by_rate({k: {'total': v['total'], 'vuln': v['vuln']} for k, v in self.by_provider.items()}, 10, min_total=1),
                'converter_top10': _top_n_by_rate(self.by_converter, 10, min_total=1),
                'attack_converter_top10': _top_n_by_rate(self.by_attack_converter, 10, min_total=1),
                'vector_converter_top20': combo_rows[:20],
                'vector_attack_converter_top20': combo_rows_attack[:20],
            },
            'unknowns': self.unknown_values.most_common(50),
            'errors': {
                'result_error_types': self.result_error_types.most_common(30),
                'error_summaries': self.error_summaries.most_common(30),
            }
        }


# -----------------------------
# JSON reading
# -----------------------------

def load_json_object(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def stream_attack_runs(path: str) -> Iterator[Dict[str, Any]]:
    if not _HAS_IJSON:
        raise RuntimeError('ijson not installed')
    with open(path, 'rb') as f:
        for item in ijson.items(f, 'campaignRun.attackRuns.item'):
            if isinstance(item, dict):
                yield item


def read_meta(path: str) -> MetaInfo:
    if _HAS_IJSON:
        meta = MetaInfo()
        with open(path, 'rb') as f:
            for prefix, event, value in ijson.parse(f):
                if event not in ('string', 'number', 'boolean', 'null'):
                    continue
                if prefix == 'campaign':
                    meta.campaign = str(value) if value is not None else ''
                elif prefix == 'campaignRun.id':
                    meta.run_id = str(value) if value is not None else ''
                elif prefix == 'campaignRun.name':
                    meta.run_name = str(value) if value is not None else ''
                elif prefix == 'campaignRun.status':
                    meta.status = str(value) if value is not None else ''
                elif prefix == 'campaignRun.createdAt':
                    meta.created_at = str(value) if value is not None else None
                elif prefix == 'campaignRun.startAt':
                    meta.start_at = str(value) if value is not None else None
                elif prefix == 'campaignRun.createdBy':
                    meta.created_by = str(value) if value is not None else ''
                elif prefix == 'campaignRun.CASIScore':
                    meta.CASIScore = _as_float(value)
                elif prefix == 'campaignRun.ARSScore':
                    meta.ARSScore = _as_float(value)
                elif prefix == 'campaignRun.casiScorePositionDelta':
                    meta.casiScorePositionDelta = _as_float(value)
                elif prefix == 'campaignRun.costOfSecurity':
                    meta.costOfSecurity = _as_float(value)
                elif prefix == 'campaignRun.rtpRatio':
                    meta.rtpRatio = _as_float(value)
                elif prefix == 'campaignRun.averagePerformance':
                    meta.averagePerformance = _as_float(value)
                elif prefix == 'campaignRun.total':
                    meta.total_field = _as_int(value, 0)
                elif prefix == 'campaignRun.actionsCount':
                    meta.actionsCount = _as_int(value, 0)
                elif prefix == 'campaignRun.progress':
                    meta.progress = _as_int(value, 0)
        return meta

    data = load_json_object(path)
    cr = data.get('campaignRun') or {}
    return MetaInfo(
        run_id=str(cr.get('id') or ''),
        run_name=str(cr.get('name') or ''),
        campaign=str(data.get('campaign') or ''),
        status=str(cr.get('status') or ''),
        created_at=cr.get('createdAt'),
        start_at=cr.get('startAt'),
        created_by=str(cr.get('createdBy') or ''),
        CASIScore=_as_float(cr.get('CASIScore')),
        ARSScore=_as_float(cr.get('ARSScore')),
        casiScorePositionDelta=_as_float(cr.get('casiScorePositionDelta')),
        costOfSecurity=_as_float(cr.get('costOfSecurity')),
        rtpRatio=_as_float(cr.get('rtpRatio')),
        averagePerformance=_as_float(cr.get('averagePerformance')),
        total_field=_as_int(cr.get('total'), 0) if cr.get('total') is not None else None,
        actionsCount=_as_int(cr.get('actionsCount'), 0) if cr.get('actionsCount') is not None else None,
        progress=_as_int(cr.get('progress'), 0) if cr.get('progress') is not None else None,
    )


# -----------------------------
# HTML template
# -----------------------------

DEFAULT_TEMPLATE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
  <style>
    body { background: #f7f8fa; }
    .container { max-width: 1200px; }
    .card { border: 0; box-shadow: 0 6px 18px rgba(0,0,0,.05); }
    .muted { color: #667085; }
    .kpi { font-size: 1.35rem; font-weight: 700; }
    .small-note { font-size: 0.88rem; color: #667085; }
    .toc a { text-decoration: none; }
    .badge-soft { background: rgba(13,110,253,.08); color: #0d6efd; }
    .table thead th { background: #f0f2f6; }
    .heat td { font-variant-numeric: tabular-nums; }
    .footer { color: #98a2b3; font-size: .85rem; }
  </style>
</head>
<body>

<div class="container my-4">
  <div class="d-flex justify-content-between align-items-start flex-wrap gap-2">
    <div>
      <h2 class="mb-1">{{ title }}</h2>
      <div class="muted">
        <span class="me-3">Campaign: <b>{{ meta.campaign or 'N/A' }}</b></span>
        <span class="me-3">Run: <b>{{ meta.run_name or 'N/A' }}</b></span>
        <span class="me-3">Run ID: <code>{{ meta.run_id or 'N/A' }}</code></span>
      </div>
      <div class="muted mt-1">
        <span class="me-3">Status: <span class="badge text-bg-secondary">{{ meta.status or 'N/A' }}</span></span>
        {% if meta.created_at %}<span class="me-3">Created: {{ meta.created_at }}</span>{% endif %}
        {% if meta.start_at %}<span class="me-3">Start: {{ meta.start_at }}</span>{% endif %}
        {% if meta.created_by %}<span class="me-3">By: {{ meta.created_by }}</span>{% endif %}
      </div>
    </div>
    <div class="text-end">
      <div class="small-note">Generated at {{ generated_at }}</div>
      <div class="small-note">Input: <code>{{ input_path }}</code></div>
      <div class="small-note">Parser: {% if has_ijson %}<span class="badge rounded-pill text-bg-success">streaming (ijson)</span>{% else %}<span class="badge rounded-pill text-bg-warning">full-load (json)</span>{% endif %}</div>
    </div>
  </div>

  <!-- KPI cards -->
  <div class="row g-3 mt-2">
    <div class="col-md-3">
      <div class="card p-3">
        <div class="muted">CASI</div>
        <div class="kpi">{{ meta.CASIScore if meta.CASIScore is not none else 'N/A' }}</div>
        <div class="small-note">casiScorePositionDelta: {{ meta.casiScorePositionDelta if meta.casiScorePositionDelta is not none else 'N/A' }}</div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card p-3">
        <div class="muted">ARS</div>
        <div class="kpi">{% if meta.ARSScore is not none %}{{ meta.ARSScore }}{% else %}<span class="muted">(not provided)</span>{% endif %}</div>
        <div class="small-note">ARSScore only shown when present in response</div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card p-3">
        <div class="muted">Overall vulnerability rate</div>
        <div class="kpi">{{ overall.vulnerability_rate | pct }}</div>
        <div class="small-note">Vulnerable {{ overall.total_vulnerable | num }} / Total {{ overall.total_tests | num }}</div>
      </div>
    </div>
    <div class="col-md-3">
      <div class="card p-3">
        <div class="muted">Coverage</div>
        <div class="kpi">{{ coverage.providers }} models</div>
        <div class="small-note">Vectors {{ coverage.vectors }}, Packs {{ coverage.packs }}, Converters(result) {{ coverage.converters }}, Converters(attack) {{ coverage.attack_converters }}, Intents {{ coverage.intentCategories }}</div>
      </div>
    </div>
  </div>

  <!-- Summary -->
  <div class="card p-3 mt-3">
    <h5 class="mb-2">Executive summary</h5>
    <ul class="mb-0">
      {% for s in summary_lines %}
      <li>{{ s }}</li>
      {% endfor %}
    </ul>
  </div>

  <!-- TOC -->
  <div class="card p-3 mt-3">
    <div class="row">
      <div class="col-md-6">
        <h6 class="mb-2">Contents</h6>
        <div class="toc">
          <div><a href="#campaign">1. Campaign-level metrics</a></div>
          <div><a href="#provider">2. Provider / Model analysis</a></div>
          <div><a href="#attack">3. Attack vector & pack</a></div>
          <div><a href="#converter">4. Converter bypass</a></div>
          <div><a href="#intent">5. Intent & severity</a></div>
          <div><a href="#conversation">6. Multi-turn analysis</a></div>
          <div><a href="#appendix">7. Appendix</a></div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="small-note">
          Notes:
          <ul>
            <li>All metrics are direct counts/ratios from response fields; no custom risk scoring.</li>
            <li>Vulnerability rate = vulnerable / total for the chosen grouping.</li>
            <li>Unknown/missing values are grouped as <code>unknown</code> and listed in Appendix.</li>
          </ul>
        </div>
      </div>
    </div>
  </div>

  <!-- 1 Campaign -->
  <div class="mt-4" id="campaign"></div>
  <h4 class="mt-4">1. Campaign-level metrics</h4>
  <div class="row g-3">
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Core run fields</h6>
        <table class="table table-sm">
          <tbody>
            <tr><th>campaignRun.total (field)</th><td>{{ meta.total_field if meta.total_field is not none else 'N/A' }}</td></tr>
            <tr><th>actionsCount</th><td>{{ meta.actionsCount if meta.actionsCount is not none else 'N/A' }}</td></tr>
            <tr><th>progress</th><td>{{ meta.progress if meta.progress is not none else 'N/A' }}</td></tr>
            <tr><th>costOfSecurity</th><td>{{ meta.costOfSecurity if meta.costOfSecurity is not none else 'N/A' }}</td></tr>
            <tr><th>rtpRatio</th><td>{{ meta.rtpRatio if meta.rtpRatio is not none else 'N/A' }}</td></tr>
            <tr><th>averagePerformance</th><td>{{ meta.averagePerformance if meta.averagePerformance is not none else 'N/A' }}</td></tr>
            <tr><th>total_errors (attackRun.errorCount sum)</th><td>{{ overall.total_errors | num }}</td></tr>
          </tbody>
        </table>
        <div class="small-note">Field <code>campaignRun.total</code> may differ from counted results; report uses counted results as ground truth for vulnerability rate.</div>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Severity highlight</h6>
        <div id="sevPie" style="height:320px;"></div>
        <div class="small-note">Critical vulnerable: {{ overall.critical_vulnerable | num }} / {{ overall.critical_total | num }} ({{ overall.critical_vulnerability_rate | pct }})</div>
      </div>
    </div>
  </div>

  <!-- 2 Provider -->
  <div class="mt-4" id="provider"></div>
  <h4 class="mt-4">2. Provider / Model analysis</h4>
  <div class="row g-3">
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Provider vulnerability rate</h6>
        <div id="providerBar" style="height:360px;"></div>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Provider table</h6>
        <div class="table-responsive">
          <table class="table table-sm">
            <thead><tr><th>Provider</th><th class="text-end">Total</th><th class="text-end">Vulnerable</th><th class="text-end">Rate</th></tr></thead>
            <tbody>
              {% for r in tables.by_provider %}
              <tr>
                <td>{{ r.name }}</td>
                <td class="text-end">{{ r.total | num }}</td>
                <td class="text-end">{{ r.vulnerable | num }}</td>
                <td class="text-end">{{ r.rate | pct }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <div class="card p-3 mt-3">
    <h6 class="mb-2">Provider × Vector matrix (vulnerability rate)</h6>
    <div class="table-responsive">
      <table class="table table-sm heat">
        <thead>
          <tr>
            <th>Provider</th>
            {% for v in coverage.vector_list %}<th class="text-end">{{ v }}</th>{% endfor %}
          </tr>
        </thead>
        <tbody>
          {% for row in matrix.provider_vector %}
          <tr>
            <td><b>{{ row.provider }}</b></td>
            {% for cell in row.cells %}
            <td class="text-end" data-rate="{{ cell.rate }}">
              {% if cell.total > 0 %}
              {{ cell.rate | pct }}<br><span class="small-note">({{ cell.vulnerable }}/{{ cell.total }})</span>
              {% else %}
              <span class="muted">—</span>
              {% endif %}
            </td>
            {% endfor %}
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    <div class="small-note">Color intensity indicates higher vulnerability rate.</div>
  </div>

  <!-- 3 Attack -->
  <div class="mt-4" id="attack"></div>
  <h4 class="mt-4">3. Attack vector & pack</h4>
  <div class="row g-3">
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Attack vector (Top by rate)</h6>
        <div id="vectorBar" style="height:420px;"></div>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Attack pack</h6>
        <div id="packBar" style="height:420px;"></div>
      </div>
    </div>
  </div>

  <div class="row g-3 mt-1">
    <div class="col-md-12">
      <div class="card p-3">
        <h6 class="mb-2">Technique (Top by rate)</h6>
        <div id="techBar" style="height:420px;"></div>
      </div>
    </div>
  </div>

  <!-- 4 Converter -->
  <div class="mt-4" id="converter"></div>
  <h4 class="mt-4">4. Converter bypass</h4>
  <div class="row g-3">
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Converter vulnerability rate (result.converter)</h6>
        <div id="convBar" style="height:360px;"></div>
        <div class="small-note">Based on <code>results.converter</code>.</div>
      </div>
      <div class="card p-3 mt-3">
        <h6 class="mb-2">Converter vulnerability rate (attack.converters[][])</h6>
        <div id="attackConvBar" style="height:360px;"></div>
        <div class="small-note">Based on flattened <code>attack.converters</code> configured per attackRun and applied to all its results.</div>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Top vector + converter combinations</h6>
        <div class="small-note">This table uses <code>results.converter</code>.</div>
        <div class="table-responsive">
          <table class="table table-sm">
            <thead><tr><th>Vector</th><th>Converter</th><th class="text-end">Total</th><th class="text-end">Vulnerable</th><th class="text-end">Rate</th></tr></thead>
            <tbody>
            {% for r in top.vector_converter_top20 %}
              <tr>
                <td>{{ r.vector }}</td>
                <td><span class="badge badge-soft">{{ r.converter }}</span></td>
                <td class="text-end">{{ r.total | num }}</td>
                <td class="text-end">{{ r.vulnerable | num }}</td>
                <td class="text-end">{{ r.rate | pct }}</td>
              </tr>
            {% endfor %}
            </tbody>
          </table>
        </div>

        <h6 class="mb-2 mt-3">Top vector + converter combinations (attack.converters)</h6>
        <div class="small-note">This table uses flattened <code>attack.converters[][]</code> from attack configuration.</div>
        <div class="table-responsive">
          <table class="table table-sm">
            <thead><tr><th>Vector</th><th>Attack Converter</th><th class="text-end">Total</th><th class="text-end">Vulnerable</th><th class="text-end">Rate</th></tr></thead>
            <tbody>
            {% for r in top.vector_attack_converter_top20 %}
              <tr>
                <td>{{ r.vector }}</td>
                <td><span class="badge badge-soft">{{ r.converter }}</span></td>
                <td class="text-end">{{ r.total | num }}</td>
                <td class="text-end">{{ r.vulnerable | num }}</td>
                <td class="text-end">{{ r.rate | pct }}</td>
              </tr>
            {% endfor %}
            </tbody>
          </table>
        </div>

      </div>
    </div>
  </div>

  <!-- 5 Intent -->
  <div class="mt-4" id="intent"></div>
  <h4 class="mt-4">5. Intent & severity</h4>
  <div class="row g-3">
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Intent category distribution</h6>
        <div id="intentBar" style="height:380px;"></div>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Intent category vulnerability rate</h6>
        <div id="intentRateBar" style="height:380px;"></div>
      </div>
    </div>
  </div>

  <div class="row g-3 mt-1">
    <div class="col-md-12">
      <div class="card p-3">
        <h6 class="mb-2">Severity distribution (count)</h6>
        <div id="sevBar" style="height:360px;"></div>
      </div>
    </div>
  </div>

  <!-- 6 Conversation -->
  <div class="mt-4" id="conversation"></div>
  <h4 class="mt-4">6. Multi-turn analysis</h4>
  <div class="row g-3">
    <div class="col-md-12">
      <div class="card p-3">
        <h6 class="mb-2">Conversation steps vs vulnerability rate</h6>
        <div id="stepsLine" style="height:380px;"></div>
        <div class="small-note">Steps are taken from <code>results.conversationSteps</code> (bucketed by exact integer; missing grouped as <code>unknown</code>).</div>
      </div>
    </div>
  </div>

  <!-- Appendix -->
  <div class="mt-4" id="appendix"></div>
  <h4 class="mt-4">7. Appendix</h4>

  <div class="row g-3">
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Unknown / missing values (Top)</h6>
        <table class="table table-sm">
          <thead><tr><th>Item</th><th class="text-end">Count</th></tr></thead>
          <tbody>
          {% for k, c in unknowns %}
            <tr><td>{{ k }}</td><td class="text-end">{{ c | num }}</td></tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card p-3">
        <h6 class="mb-2">Result errors</h6>
        <div class="row">
          <div class="col-6">
            <div class="small-note">error (top)</div>
            <table class="table table-sm">
              <tbody>
              {% for k, c in errors.result_error_types %}
                <tr><td>{{ k }}</td><td class="text-end">{{ c | num }}</td></tr>
              {% endfor %}
              </tbody>
            </table>
          </div>
          <div class="col-6">
            <div class="small-note">errorSummary (top)</div>
            <table class="table table-sm">
              <tbody>
              {% for k, c in errors.error_summaries %}
                <tr><td>{{ k }}</td><td class="text-end">{{ c | num }}</td></tr>
              {% endfor %}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer mt-4 mb-3">
    Generated by <code>campaign_run_analyzer_v2.py</code>. Charts by Plotly.js (CDN). Styling by Bootstrap.
  </div>
</div>

<script>
  const DATA = {{ chart_data_json | safe }};

  function barRate(divId, rows, title, topN=15) {
    const sorted = [...rows].sort((a,b)=> (b.rate-a.rate) || (b.total-a.total)).slice(0, topN);
    const x = sorted.map(r=>r.name);
    const y = sorted.map(r=>Math.round(r.rate*10000)/100);
    const text = sorted.map(r=>`vuln ${r.vulnerable}/${r.total}`);
    const trace = {type:'bar', x, y, text, hovertemplate:'%{x}<br>%{y}%<br>%{text}<extra></extra>'};
    const layout = {title, yaxis:{title:'Vulnerability rate (%)'}, margin:{l:50,r:20,t:40,b:120}};
    Plotly.newPlot(divId, [trace], layout, {displayModeBar:false, responsive:true});
  }

  function barCount(divId, rows, title, topN=15) {
    const sorted = [...rows].sort((a,b)=> (b.total-a.total)).slice(0, topN);
    const x = sorted.map(r=>r.name);
    const y = sorted.map(r=>r.total);
    const trace = {type:'bar', x, y, hovertemplate:'%{x}<br>%{y}<extra></extra>'};
    const layout = {title, yaxis:{title:'Count'}, margin:{l:50,r:20,t:40,b:120}};
    Plotly.newPlot(divId, [trace], layout, {displayModeBar:false, responsive:true});
  }

  function pie(divId, rows, title) {
    const labels = rows.map(r=>r.name);
    const values = rows.map(r=>r.total);
    const trace = {type:'pie', labels, values, textinfo:'label+percent'};
    Plotly.newPlot(divId, [trace], {title, margin:{l:10,r:10,t:40,b:10}}, {displayModeBar:false, responsive:true});
  }

  function lineRate(divId, rows, title) {
    const cleaned = rows
      .filter(r => r.name !== 'unknown')
      .map(r => ({...r, steps: parseInt(r.name,10)}))
      .filter(r => !Number.isNaN(r.steps))
      .sort((a,b)=>a.steps-b.steps);

    const x = cleaned.map(r=>r.steps);
    const y = cleaned.map(r=>Math.round(r.rate*10000)/100);
    const size = cleaned.map(r=>Math.max(6, Math.min(18, Math.sqrt(r.total))));
    const text = cleaned.map(r=>`total ${r.total}, vuln ${r.vulnerable}`);

    const trace = {type:'scatter', mode:'lines+markers', x, y, text, marker:{size}, hovertemplate:'steps %{x}<br>%{y}%<br>%{text}<extra></extra>'};
    const layout = {title, xaxis:{title:'Conversation steps'}, yaxis:{title:'Vulnerability rate (%)'}, margin:{l:50,r:20,t:40,b:60}};
    Plotly.newPlot(divId, [trace], layout, {displayModeBar:false, responsive:true});
  }

  // Render charts
  barRate('providerBar', DATA.by_provider, 'Provider vulnerability rate', 20);
  barRate('vectorBar', DATA.by_vector, 'Attack vector vulnerability rate (Top)', 20);
  barRate('packBar', DATA.by_pack, 'Attack pack vulnerability rate', 20);
  barRate('convBar', DATA.by_converter, 'Converter vulnerability rate (result.converter)', 20);
  barRate('attackConvBar', DATA.by_attack_converter || [], 'Converter vulnerability rate (attack.converters)', 20);
  barRate('intentRateBar', DATA.by_intent_cat, 'Intent category vulnerability rate', 20);
  barCount('intentBar', DATA.by_intent_cat, 'Intent category distribution (count)', 20);
  barCount('sevBar', DATA.by_severity, 'Severity distribution (count)', 20);
  pie('sevPie', DATA.by_severity, 'Severity distribution');
  barRate('techBar', DATA.by_technique, 'Technique vulnerability rate (Top)', 20);
  lineRate('stepsLine', DATA.by_steps, 'Conversation steps vs vulnerability rate');

  // Heatmap-like table cell background
  (function colorizeHeatTable(){
    const cells = document.querySelectorAll('td[data-rate]');
    cells.forEach(td => {
      const r = parseFloat(td.getAttribute('data-rate'));
      if (Number.isNaN(r)) return;
      const a = Math.min(0.38, Math.max(0, r)) * 0.38;
      td.style.backgroundColor = `rgba(220, 53, 69, ${a})`;
    });
  })();
</script>

</body>
</html>
"""


def render_html(meta: MetaInfo, analysis: Dict[str, Any], title: str, input_path: str, template_path: Optional[str] = None) -> str:
    chart_data = {
        'by_provider': analysis['tables']['by_provider'],
        'by_vector': analysis['tables']['by_vector'],
        'by_pack': analysis['tables']['by_pack'],
        'by_converter': analysis['tables']['by_converter'],
        'by_attack_converter': analysis['tables']['by_attack_converter'],
        'by_intent_cat': analysis['tables']['by_intent_cat'],
        'by_severity': analysis['tables']['by_severity'],
        'by_technique': analysis['tables']['by_technique'],
        'by_steps': analysis['tables']['by_steps'],
    }

    ov = analysis['overall']
    cov = analysis['coverage']

    def leader(rows: List[Dict[str, Any]]):
        return rows[0] if rows else None

    vec_leader = leader(analysis['tables']['by_vector'])
    pack_leader = leader(analysis['tables']['by_pack'])
    prov_leader = leader(analysis['tables']['by_provider'])

    summary_lines: List[str] = []
    summary_lines.append(
        f"Tested {ov['total_tests']:,} prompts across {cov['providers']} providers, {cov['vectors']} attack vectors and {cov['packs']} packs; overall vulnerability rate {ov['vulnerability_rate']*100:.2f}%."
    )
    if prov_leader and prov_leader['total'] > 0:
        summary_lines.append(
            f"Highest provider vulnerability rate: {prov_leader['name']} ({prov_leader['rate']*100:.2f}%, {prov_leader['vulnerable']}/{prov_leader['total']})."
        )
    if vec_leader and vec_leader['total'] > 0:
        summary_lines.append(
            f"Highest vector vulnerability rate: {vec_leader['name']} ({vec_leader['rate']*100:.2f}%, {vec_leader['vulnerable']}/{vec_leader['total']})."
        )
    if pack_leader and pack_leader['total'] > 0:
        summary_lines.append(
            f"Highest pack vulnerability rate: {pack_leader['name']} ({pack_leader['rate']*100:.2f}%, {pack_leader['vulnerable']}/{pack_leader['total']})."
        )
    if ov['critical_total']:
        summary_lines.append(
            f"Critical severity: {ov['critical_vulnerable']:,} vulnerable out of {ov['critical_total']:,} tests ({ov['critical_vulnerability_rate']*100:.2f}%)."
        )
    if cov.get('attack_converters', 0):
        summary_lines.append(
            f"Attack configuration converters coverage: {cov['attack_converters']} unique (from attack.converters[][]), separate from {cov['converters']} result-level converters (results.converter)."
        )

    generated_at = _dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')
    if template_path:
        tpl_dir = os.path.dirname(os.path.abspath(template_path)) or '.'
        tpl_name = os.path.basename(template_path)
        env = Environment(loader=FileSystemLoader(tpl_dir), autoescape=select_autoescape(['html', 'xml']))
    else:
        env = Environment(autoescape=select_autoescape(['html', 'xml']))

    # Register filters BEFORE compiling/loading templates
    env.filters['pct'] = _fmt_pct
    env.filters['num'] = _fmt_num

    if template_path:
        template = env.get_template(tpl_name)
    else:
        template = env.from_string(DEFAULT_TEMPLATE)
    meta.created_at = _iso_to_local(meta.created_at)
    meta.start_at = _iso_to_local(meta.start_at)

    return template.render(
        title=title,
        meta=meta,
        overall=analysis['overall'],
        coverage=analysis['coverage'],
        tables={k: analysis['tables'][k] for k in analysis['tables']},
        matrix=analysis['matrix'],
        top=analysis['top'],
        unknowns=analysis['unknowns'],
        errors=analysis['errors'],
        summary_lines=summary_lines,
        generated_at=generated_at,
        input_path=input_path,
        has_ijson=_HAS_IJSON,
        chart_data_json=json.dumps(chart_data, ensure_ascii=False),
    )


# -----------------------------
# CLI
# -----------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Analyze campaign_run JSON and generate an HTML report.')
    parser.add_argument('--input', required=True, help='Path to campaign_run JSON file (full response export).')
    parser.add_argument('--output', default=None, help='Output HTML path. Default: <input_dir>/campaign_run_report.html')
    parser.add_argument('--title', default=None, help='Report title. Default: campaignRun.name if available.')
    parser.add_argument('--template', default=None, help='Optional Jinja2 HTML template file path.')
    parser.add_argument('--no-stream', action='store_true', help='Disable streaming even if ijson is available.')
    args = parser.parse_args(argv)

    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 2

    output_path = args.output or os.path.join(os.path.dirname(input_path), 'campaign_run_report.html')
    output_path = os.path.abspath(output_path)

    meta = read_meta(input_path)
    title = args.title or meta.run_name or 'Campaign Run Report'

    analyzer = Analyzer()

    use_stream = _HAS_IJSON and (not args.no_stream)
    if use_stream:
        try:
            for ar in stream_attack_runs(input_path):
                analyzer.consume_attack_run(ar)
        except Exception as e:
            print(f"WARN: streaming failed ({e}); falling back to full JSON load.", file=sys.stderr)
            use_stream = False

    if not use_stream:
        data = load_json_object(input_path)
        cr = data.get('campaignRun') or {}
        attack_runs = cr.get('attackRuns') or []
        if not isinstance(attack_runs, list):
            print('ERROR: campaignRun.attackRuns not found or not a list.', file=sys.stderr)
            attack_runs = []
        for ar in attack_runs:
            if isinstance(ar, dict):
                analyzer.consume_attack_run(ar)

    analysis = analyzer.finalize()
    html = render_html(meta, analysis, title=title, input_path=input_path, template_path=args.template)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"OK: report written to {output_path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
