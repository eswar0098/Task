from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parents[1]
DATA_PATH = BASE / 'data' / 'maintenance_tickets.csv'
FRONTEND_DIR = BASE / 'frontend'

ROOT_CAUSE_RULES = {
    'inverter_thermal': 'Thermal stress in the inverter or cooling loop, likely caused by overheating or reduced airflow.',
    'gearbox_vibration': 'Mechanical imbalance or bearing degradation in the gearbox, often worsened by lubrication loss or misalignment.',
    'inspection_compliance': 'Inspection workflow backlog or delayed preventive maintenance, leading to non-compliance risk.',
    'data_gap': 'SCADA or telemetry communication issue causing missing measurements or sensor dropout.',
    'pitch_system': 'Pitch actuator or control-loop failure triggered by environmental load changes or actuator drift.',
    'grid_curtailment': 'Grid dispatch or curtailment setting mismatch between the generation control layer and the grid operator instructions.'
}

NEXT_ACTION_RULES = {
    'inverter_thermal': 'Inspect inverter cooling fans, DC bus temperatures, and perform a thermal scan; isolate the unit if temperatures remain above threshold.',
    'gearbox_vibration': 'Stop the unit for a gearbox inspection, check lubrication quality, vibration spectrum, and validate bearing condition before restart.',
    'inspection_compliance': 'Close the inspection backlog and schedule the required compliance check with a preventive maintenance follow-up.',
    'data_gap': 'Validate SCADA connectivity, sensor health, and gateway logs; restore telemetry before relying on the data for dispatch decisions.',
    'pitch_system': 'Check pitch actuator response, control software alarms, and mechanical range limits before returning the turbine to service.',
    'grid_curtailment': 'Verify the curtailment profile with the grid operator and reconcile the dispatch instructions in the SCADA and generation logic.'
}

ROUTING_TEAM = {
    'inverter_thermal': 'Electrical Maintenance Team',
    'gearbox_vibration': 'Mechanical Reliability Team',
    'inspection_compliance': 'Operations Compliance Team',
    'data_gap': 'SCADA / OT Data Engineering Team',
    'pitch_system': 'Controls & Turbine Systems Team',
    'grid_curtailment': 'Grid Operations Team'
}

CATEGORY_RULES = {
    'inverter_thermal': ['inverter', 'thermal', 'temperature', 'overheat', 'trip', 'fault', 'cooling'],
    'gearbox_vibration': ['gearbox', 'vibration', 'vibrating', 'noise', 'bearing', 'shaft', 'rumble'],
    'inspection_compliance': ['inspection', 'checklist', 'compliance', 'audit', 'pending', 'delayed', 'maintenance'],
    'data_gap': ['scada', 'telemetry', 'missing', 'sensor', 'data', 'dashboard', 'signal', 'connection'],
    'pitch_system': ['pitch', 'blade', 'actuator', 'yaw', 'control', 'error', 'gust'],
    'grid_curtailment': ['curtailment', 'grid', 'dispatch', 'generation', 'load', 'operator', 'dashboard']
}


def normalize_text(value: str) -> str:
    return re.sub(r'[^a-z0-9\s]', ' ', value.lower())


def tokenize(text: str) -> set[str]:
    return set(normalize_text(text).split())


def load_training_examples() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with DATA_PATH.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({
                'asset_type': (row.get('asset_type') or '').strip(),
                'description': (row.get('description') or '').strip(),
                'target_category': (row.get('target_category') or '').strip()
            })
    return rows


def predict_category(text: str, asset_type: str) -> Tuple[str, float, List[str]]:
    candidates = defaultdict(float)
    evidence: List[str] = []
    tokens = tokenize(f'{asset_type} {text}')

    for category, keywords in CATEGORY_RULES.items():
        score = 0.0
        matched = []
        for keyword in keywords:
            if keyword in tokens:
                score += 2.5
                matched.append(keyword)
        candidates[category] = score
        if matched:
            evidence.append(f'{category}:{", ".join(matched)}')

    for row in load_training_examples():
        row_tokens = tokenize(f"{row['asset_type']} {row['description']}")
        overlap = len(tokens & row_tokens)
        if overlap:
            candidates[row['target_category']] += overlap * 0.7

    if not any(candidates.values()):
        return 'inspection_compliance', 0.26, ['no strong keyword match']

    best_category, best_score = max(candidates.items(), key=lambda item: item[1])
    total = sum(candidates.values())
    confidence = best_score / total if total else 0.0
    return best_category, max(0.05, min(0.99, confidence)), evidence


def severity_from_signals(text: str, category: str) -> Tuple[int, str, List[str]]:
    lowered = normalize_text(text)
    evidence: List[str] = []
    score = 45

    category_severity = {
        'gearbox_vibration': 90,
        'pitch_system': 78,
        'inverter_thermal': 80,
        'grid_curtailment': 60,
        'data_gap': 52,
        'inspection_compliance': 38
    }
    score = max(score, category_severity.get(category, 50))

    severe_terms = ['fire', 'smoke', 'critical', 'trip', 'shutdown', 'loss of generation', 'high temperature', 'abnormal noise', 'sudden', 'failure']
    moderate_terms = ['warning', 'alert', 'degradation', 'error', 'unstable', 'missing', 'delayed', 'pending']

    for term in severe_terms:
        if term in lowered:
            score += 12
            evidence.append(f'severity signal: {term}')
    for term in moderate_terms:
        if term in lowered:
            score += 5
            evidence.append(f'operational signal: {term}')

    if 'critical' in lowered:
        score += 10
    if 'inspection' in lowered or 'checklist' in lowered:
        score = min(score, 60)

    score = max(0, min(100, score))
    if score >= 85:
        label = 'critical'
    elif score >= 65:
        label = 'high'
    elif score >= 45:
        label = 'medium'
    else:
        label = 'low'
    return score, label, evidence


def route_decision(text: str, category: str) -> Tuple[str, List[str]]:
    lowered = normalize_text(text)
    evidence: List[str] = []
    if any(term in lowered for term in ['trip', 'overheat', 'temperature', 'thermal']):
        evidence.append('thermal risk')
    if any(term in lowered for term in ['vibration', 'noise', 'bearing', 'gearbox']):
        evidence.append('mechanical risk')
    if any(term in lowered for term in ['inspection', 'checklist', 'compliance', 'audit']):
        evidence.append('compliance risk')
    if any(term in lowered for term in ['data', 'missing', 'telemetry', 'scada', 'sensor']):
        evidence.append('data quality risk')
    if any(term in lowered for term in ['pitch', 'actuator', 'blade']):
        evidence.append('controls risk')
    if any(term in lowered for term in ['curtailment', 'grid', 'dispatch', 'generation dashboard']):
        evidence.append('grid coordination risk')

    team = ROUTING_TEAM.get(category, 'Asset Operations Team')
    return team, evidence


def analyze_ticket(text: str, asset_type: str) -> Dict:
    if not text or not text.strip():
        raise ValueError('Ticket text is required.')

    training_rows = load_training_examples()
    category, confidence, keyword_evidence = predict_category(text, asset_type)
    severity_score, severity_label, severity_evidence = severity_from_signals(text, category)
    routing_team, route_evidence = route_decision(text, category)

    return {
        'status': 'ok',
        'input': {'asset_type': asset_type or 'unknown', 'text': text.strip()},
        'prediction': {
            'category': category,
            'confidence': round(float(confidence), 3),
            'severity_score': severity_score,
            'severity': severity_label,
            'root_cause': ROOT_CAUSE_RULES.get(category, 'Root cause needs a field technician inspection and sensor review.'),
            'recommended_next_action': NEXT_ACTION_RULES.get(category, 'Review maintenance records and dispatch a technician for a field inspection.'),
            'routing_team': routing_team,
            'evidence': sorted(set(keyword_evidence + route_evidence + severity_evidence))
        },
        'model_metrics': {
            'dataset_rows': len(training_rows),
            'categories': sorted({row['target_category'] for row in training_rows}),
            'method': 'keyword + similarity scoring over bundled dataset'
        }
    }


class TriageRequestHandler(BaseHTTPRequestHandler):
    server_version = 'TicketTriage/1.0'

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path

        if route in ('/', '/index.html'):
            self._serve_file(FRONTEND_DIR / 'index.html', 'text/html; charset=utf-8')
            return

        if route == '/api/demo':
            payload = {
                'case_study': 'AI Agent for Maintenance Ticket Prioritization',
                'status': 'app running',
                'expected_outcome': 'A ticket triage system that assigns severity, category, probable root cause, and next action using NLP and rule/tool-based agent logic.',
                'sample_payload': {
                    'asset_type': 'solar',
                    'text': 'Inverter 4 tripping repeatedly after noon, high temperature alarm visible.'
                }
            }
            self._send_json(payload)
            return

        if route == '/health':
            self._send_json({'status': 'healthy'})
            return

        static_path = FRONTEND_DIR / route.lstrip('/')
        if route.startswith('/static/') and static_path.exists():
            self._serve_file(static_path, self._guess_content_type(static_path))
            return

        self._send_json({'detail': 'Not found'}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/api/run':
            self._send_json({'detail': 'Not found'}, status=404)
            return

        try:
            content_length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode('utf-8') or '{}')
            text = str(payload.get('text', '')).strip()
            asset_type = str(payload.get('asset_type', 'solar')).strip() or 'solar'
            if not text:
                raise ValueError('Ticket text is required.')
            response = analyze_ticket(text, asset_type)
            self._send_json(response)
        except Exception as exc:
            self._send_json({'detail': str(exc)}, status=400)

    def _serve_file(self, file_path: Path, content_type: str):
        try:
            data = file_path.read_bytes()
        except FileNotFoundError:
            self._send_json({'detail': 'File not found'}, status=404)
            return

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _guess_content_type(self, path: Path) -> str:
        suffix = path.suffix.lower()
        mapping = {
            '.html': 'text/html; charset=utf-8',
            '.css': 'text/css; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8',
            '.json': 'application/json; charset=utf-8',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.svg': 'image/svg+xml'
        }
        return mapping.get(suffix, 'application/octet-stream')

    def _send_json(self, payload: Dict, status: int = 200):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args):
        return


def run_server():
    host = '0.0.0.0'
    port = int(os.environ.get('PORT', '8000'))
    server = ThreadingHTTPServer((host, port), TriageRequestHandler)
    print(f'Running maintenance ticket triage app on http://{host}:{port}')
    server.serve_forever()


if __name__ == '__main__':
    run_server()

