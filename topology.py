import json
import math
import os

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsGeometry, QgsSpatialIndex


class TopologyValidator:
    def __init__(self, plugin):
        self.plugin = plugin

    def _read_text_file(self, path: str):
        for encoding in ("utf-8", "cp1251"):
            try:
                with open(path, "r", encoding=encoding) as handle:
                    return handle.read()
            except UnicodeDecodeError:
                continue
            except Exception:
                break
        return ""

    def load_rules(self):
        rules = []
        rules_path = os.path.join(self.plugin.plugin_dir, "templates", "topo_rules.txt")
        content = self._read_text_file(rules_path)
        if not content:
            return rules
        phrases = [
            ("не повинні перекриватися самі себе", "no_overlap_self"),
            ("не повинні перекриватися з", "no_overlap"),
            ("не повинні перекриватися", "no_overlap"),
            ("не повинні мати проміжків", "no_gaps"),
            ("не повинні мати висячих вузлів", "no_dangling"),
            ("мають складатися з однієї частини", "singlepart"),
            ("мають суміщатися з об'єктами", "must_intersect"),
        ]
        for raw in content.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            src = line.split()[0]
            rule_type = None
            target = None
            for phrase, rtype in phrases:
                if phrase in line:
                    rule_type = rtype
                    if rtype in {"no_overlap", "must_intersect"}:
                        target = line.split()[-1]
                    elif rtype == "no_overlap_self":
                        target = src
                    else:
                        target = src
                    break
            if rule_type:
                rules.append({"src": src, "type": rule_type, "target": target, "raw": line})
        return rules

    def _geometry_to_geojson(self, geom: QgsGeometry):
        if geom is None or geom.isEmpty():
            return None
        try:
            return json.loads(geom.asJson())
        except Exception:
            return None

    def _topo_error_entry(self, class_key: str, geom: QgsGeometry, message: str):
        return {
            "layer": class_key,
            "feature_index": None,
            "feature_id": None,
            "geometry": self._geometry_to_geojson(geom),
            "messages": [message],
        }

    def _check_must_intersect(self, layer_a, layer_b, name_b: str):
        entries = []
        if layer_a is None or layer_b is None:
            return entries
        index_b = QgsSpatialIndex(layer_b.getFeatures())
        for feature in layer_a.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            hits = index_b.intersects(geom.boundingBox())
            ok = False
            for fid in hits:
                other = layer_b.getFeature(fid)
                if other is None:
                    continue
                other_geom = other.geometry()
                if other_geom is not None and geom.intersects(other_geom):
                    ok = True
                    break
            if not ok:
                entries.append(self._topo_error_entry(layer_a.name(), geom, f"Топологія: не суміщується з {name_b}."))
        return entries

    def _check_no_overlap(self, layer_a, layer_b, name_b: str, same_layer: bool = False):
        entries = []
        if layer_a is None or layer_b is None:
            return entries
        index_b = QgsSpatialIndex(layer_b.getFeatures())
        for feature in layer_a.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            hits = index_b.intersects(geom.boundingBox())
            for fid in hits:
                if same_layer and fid == feature.id():
                    continue
                other = layer_b.getFeature(fid)
                if other is None:
                    continue
                other_geom = other.geometry()
                if other_geom is None or other_geom.isEmpty():
                    continue
                if geom.overlaps(other_geom) or geom.equals(other_geom):
                    entries.append(self._topo_error_entry(layer_a.name(), geom, f"Топологія: перекривання з {name_b}."))
                    break
        return entries

    def _check_no_dangling(self, layer_a):
        entries = []
        if layer_a is None:
            return entries
        index = QgsSpatialIndex(layer_a.getFeatures())
        for feature in layer_a.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            try:
                start = geom.vertexAt(0)
                end = geom.vertexAt(geom.vertexCount() - 1)
            except Exception:
                continue
            for point in (start, end):
                try:
                    pgeom = QgsGeometry.fromPointXY(point)
                except Exception:
                    continue
                hits = index.intersects(pgeom.boundingBox())
                has_other = False
                for fid in hits:
                    if fid == feature.id():
                        continue
                    other = layer_a.getFeature(fid)
                    if other is None:
                        continue
                    other_geom = other.geometry()
                    if other_geom is not None and pgeom.intersects(other_geom):
                        has_other = True
                        break
                if not has_other:
                    entries.append(self._topo_error_entry(layer_a.name(), pgeom, "Топологія: висячий вузол."))
        return entries

    def _check_singlepart(self, layer_a):
        entries = []
        if layer_a is None:
            return entries
        for feature in layer_a.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            if geom.isMultipart():
                entries.append(self._topo_error_entry(layer_a.name(), geom, "Топологія: має бути одна частина."))
        return entries

    def _check_no_gaps(self, layer_a):
        entries = []
        if layer_a is None:
            return entries
        geoms = [f.geometry() for f in layer_a.getFeatures() if f.geometry() and not f.geometry().isEmpty()]
        if not geoms:
            return entries
        try:
            union_geom = QgsGeometry.unaryUnion(geoms)
        except Exception:
            return entries
        if union_geom is None or union_geom.isEmpty():
            return entries
        try:
            if union_geom.isMultipart():
                polygons = union_geom.asMultiPolygon()
            else:
                polygons = [union_geom.asPolygon()]
        except Exception:
            return entries
        for poly in polygons:
            if not poly or len(poly) < 2:
                continue
            for ring in poly[1:]:
                try:
                    hole_geom = QgsGeometry.fromPolygonXY([ring])
                except Exception:
                    continue
                if hole_geom is None or hole_geom.isEmpty():
                    continue
                try:
                    area = float(hole_geom.area())
                except Exception:
                    area = 0.0
                try:
                    perimeter = float(hole_geom.length())
                except Exception:
                    perimeter = 0.0
                if area > 0.0 and perimeter > 0.0:
                    form_factor = (perimeter * perimeter) / (4.0 * math.pi * area)
                else:
                    form_factor = float("inf")
                message = self.plugin.tr(u"Топологія: проміжок, площа {0:.3f} м², форм-фактор {1:.6E}.").format(
                    area,
                    form_factor,
                )
                entries.append(self._topo_error_entry(layer_a.name(), hole_geom, message))
        return entries

    def run_validation(self, rules=None, progress=None):
        errors_by_class = {}
        rule_records = []
        if rules is None:
            rules = self.load_rules()
        if not rules:
            rule_records.append(
                {
                    "check": "topology_rules",
                    "file": "topo_rules.txt",
                    "status": "ok",
                    "message": "У topo_rules.txt не знайдено активних топологічних правил.",
                }
            )
            return errors_by_class, rule_records
        total = len(rules)
        for idx, rule in enumerate(rules, start=1):
            if progress is not None:
                if progress.wasCanceled():
                    break
                progress.setLabelText(self.plugin.tr(u"Топологія: {0}/{1}").format(idx, total))
                progress.setValue(idx - 1)
                QCoreApplication.processEvents()
            src = rule["src"]
            target = rule["target"]
            rtype = rule["type"]
            raw_rule = str(rule.get("raw") or "").strip()
            rule_label = raw_rule or f"{src} [{rtype}] {target}"
            layer_a = self.plugin._get_layer_for_class(src)
            missing_layers = []
            if layer_a is None:
                missing_layers.append(src)
            layer_b = None
            if rtype in {"must_intersect", "no_overlap"}:
                if target == src:
                    layer_b = layer_a
                else:
                    layer_b = self.plugin._get_layer_for_class(target)
                    if layer_b is None:
                        missing_layers.append(target)
            if missing_layers:
                rule_records.append(
                    {
                        "check": "topology_rules",
                        "file": f"{src}.geojson",
                        "status": "skipped",
                        "message": "Правило не застосовано: "
                        + rule_label
                        + ". Відсутні шари: "
                        + ", ".join(sorted(set(missing_layers))),
                    }
                )
                continue
            if rtype == "must_intersect":
                entries = self._check_must_intersect(layer_a, layer_b, target)
            elif rtype == "no_overlap":
                entries = self._check_no_overlap(layer_a, layer_b, target, same_layer=(src == target))
            elif rtype == "no_overlap_self":
                entries = self._check_no_overlap(layer_a, layer_a, src, same_layer=True)
            elif rtype == "no_dangling":
                entries = self._check_no_dangling(layer_a)
            elif rtype == "singlepart":
                entries = self._check_singlepart(layer_a)
            elif rtype == "no_gaps":
                entries = self._check_no_gaps(layer_a)
            else:
                entries = []
            if entries:
                errors_by_class.setdefault(src, []).extend(entries)
                rule_records.append(
                    {
                        "check": "topology_rules",
                        "file": f"{src}.geojson",
                        "status": "error",
                        "message": f"Застосовано правило: {rule_label}. Виявлено порушень: {len(entries)}.",
                    }
                )
            else:
                rule_records.append(
                    {
                        "check": "topology_rules",
                        "file": f"{src}.geojson",
                        "status": "ok",
                        "message": f"Застосовано правило: {rule_label}. Порушень не виявлено.",
                    }
                )
        if progress is not None:
            progress.setValue(total)
        return errors_by_class, rule_records
