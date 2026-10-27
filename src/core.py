"""SMART normalization and configurable, conservative alert evaluation."""
import copy
import hashlib
import math

DEFAULT_RULES = [
    dict(metric='health_failed', label='SMART-Gesamtstatus fehlgeschlagen', yellow=1, red=1),
    dict(metric='critical_warning', label='NVMe kritische Warnbits', yellow=1, red=1),
    dict(metric='ata_5', label='HDD: neu zugewiesene Sektoren', yellow=1, red=None),
    dict(metric='ata_187', label='Nicht korrigierbare gemeldete Fehler', yellow=1, red=1),
    dict(metric='ata_188', label='Befehls-Zeitüberschreitungen (herstellerspezifisch)', yellow=1, red=None),
    dict(metric='ata_197', label='HDD: schwebende Sektoren', yellow=1, red=1),
    dict(metric='ata_198', label='HDD: nicht korrigierbare Sektoren', yellow=1, red=1),
    dict(metric='ata_199', label='Schnittstellen-CRC (Kabel/Controller prüfen)', yellow=1, red=None, mode='delta'),
    dict(metric='temperature', label='Temperatur °C (an Modell anpassen)', yellow=50, red=60),
    dict(metric='percentage_used', label='SSD: verbrauchte Lebensdauer %', yellow=80, red=100),
    dict(metric='spare_margin', label='NVMe: Reserve minus Herstellergrenze', yellow=5, red=0, direction='below'),
    dict(metric='media_errors', label='NVMe: Medien-/Integritätsfehler', yellow=1, red=1),
    dict(metric='scsi_defects', label='SAS/SCSI: gewachsene Defektliste', yellow=1, red=None),
    dict(metric='scsi_uncorrected', label='SAS/SCSI: unkorrigierte Fehler', yellow=1, red=1),
    dict(metric='ata_threshold_failed', label='ATA: aktueller Herstellergrenzwert unterschritten', yellow=1, red=1),
]

def defaults():
    rules = copy.deepcopy(DEFAULT_RULES)
    for r in rules:
        r.setdefault('enabled', True)
        r.setdefault('direction', 'above')
        r.setdefault('mode', 'absolute')
        r.setdefault('drive', '')
    return rules

def number(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
        return v
    return None

def normalize(data, device):
    metrics = {}
    def put(k, v):
        if number(v) is not None:
            metrics[k] = v
    status = data.get('smart_status', {}).get('passed')
    if isinstance(status, bool):
        metrics['health_failed'] = int(not status)
    put('temperature', data.get('temperature', {}).get('current'))
    put('power_on_hours', data.get('power_on_time', {}).get('hours'))
    put('power_cycles', data.get('power_cycle_count'))
    put('percentage_used', data.get('endurance_used', {}).get('current_percent'))
    put('available_spare', data.get('spare_available', {}).get('current_percent'))
    put('available_spare_threshold', data.get('spare_available', {}).get('threshold_percent'))
    attrs = data.get('ata_smart_attributes', {}).get('table', [])
    failed = 0
    for a in attrs:
        put('ata_' + str(a['id']), a.get('raw', {}).get('value'))
        if a.get('when_failed') == 'now':
            failed += 1
    if attrs:
        metrics['ata_threshold_failed'] = failed
    nvme = data.get('nvme_smart_health_information_log', {})
    for k in ('critical_warning', 'available_spare', 'available_spare_threshold', 'percentage_used',
              'media_errors', 'num_err_log_entries', 'unsafe_shutdowns', 'power_on_hours',
              'power_cycles', 'data_units_read', 'data_units_written', 'warning_temp_time', 'critical_comp_time'):
        put(k, nvme.get(k))
    if 'critical_warning' in metrics:
        for bit, label in enumerate(('spare_low','temperature','reliability','read_only','backup_failed','persistent_memory')):
            metrics['nvme_warning_'+label] = int(bool(metrics['critical_warning'] & (1 << bit)))
    if 'available_spare' in metrics and 'available_spare_threshold' in metrics:
        metrics['spare_margin'] = metrics['available_spare'] - metrics['available_spare_threshold']
    put('scsi_defects', data.get('scsi_grown_defect_list'))
    uncorrected = [x.get('total_uncorrected_errors') for x in data.get('scsi_error_counter_log', {}).values() if isinstance(x, dict)]
    if any(number(x) is not None for x in uncorrected):
        metrics['scsi_uncorrected'] = sum(x for x in uncorrected if number(x) is not None)
    model = data.get('model_name') or data.get('scsi_model_name') or data.get('product') or device['name']
    serial = data.get('serial_number', '')
    identity = (model + '|' + serial) if serial else device['name'] + '|' + device.get('type', '')
    errors = [m.get('string', '') for m in data.get('smartctl', {}).get('messages', [])]
    exit_status = data.get('smartctl', {}).get('exit_status', 0)
    readable = status is not None or bool(attrs) or bool(nvme) or 'scsi_uncorrected' in metrics
    return dict(id=hashlib.sha256(identity.encode()).hexdigest()[:24], model=model, serial=serial,
                device=device['name'], protocol=data.get('device', {}).get('protocol', device.get('type', '?')),
                capacity=data.get('user_capacity', {}).get('bytes'), metrics=metrics,
                readable=readable, partial=bool(exit_status & 7), messages=errors,
                attributes=attrs, raw=data)

def evaluate(drive, previous, rules):
    alerts = []
    current = drive.get('metrics', {})
    old = (previous or {}).get('metrics', {})
    for rule in rules:
        if not rule.get('enabled', True) or rule.get('drive', '') not in ('', drive['id']):
            continue
        key = rule['metric']
        value = number(current.get(key))
        if value is None:
            continue
        if rule.get('mode') == 'delta':
            prev = number(old.get(key))
            if prev is None or value < prev:
                continue  # First measurement / counter reset is not a new error.
            value -= prev
        compare = (lambda a, b: a <= b) if rule.get('direction') == 'below' else (lambda a, b: a >= b)
        level = None
        for color in ('yellow', 'red'):
            limit = number(rule.get(color))
            if limit is not None and compare(value, limit):
                level = color
        if level:
            alerts.append(dict(level=level, metric=key, label=rule.get('label', key), value=value,
                               mode=rule.get('mode', 'absolute')))
    level = 'red' if any(a['level'] == 'red' for a in alerts) else 'yellow' if alerts else 'green'
    if not alerts and (not drive.get('readable') or drive.get('partial')):
        level = 'unknown'
    return dict(level=level, alerts=alerts)

def validate_rules(rules):
    if not isinstance(rules, list) or len(rules) > 256:
        raise ValueError('Maximal 256 Regeln erlaubt.')
    for r in rules:
        if not isinstance(r, dict) or not isinstance(r.get('metric'), str) or not r['metric']:
            raise ValueError('Jede Regel braucht einen Messwert-Schlüssel.')
        if r.get('mode') not in ('absolute', 'delta') or r.get('direction') not in ('above', 'below'):
            raise ValueError('Ungültige Vergleichsart.')
        for c in ('yellow', 'red'):
            if r.get(c) is not None and number(r[c]) is None:
                raise ValueError('Grenzwerte müssen endliche Zahlen oder leer sein.')
        y, red = r.get('yellow'), r.get('red')
        if y is not None and red is not None and ((r['direction'] == 'above' and red < y) or (r['direction'] == 'below' and red > y)):
            raise ValueError('Rot muss mindestens so kritisch wie Gelb sein.')
        if not isinstance(r.get('enabled'), bool) or not isinstance(r.get('drive', ''), str):
            raise ValueError('Ungültiger Regelbereich.')
    return rules
