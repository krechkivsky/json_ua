import json
import re


class SyntaxValidator:
    METADATA_CLASS_KEY = "metadata"
    METADATA_FILE_CLASS_PATTERN = re.compile(r"^\d{10}_metadata$", re.IGNORECASE)
    PLAN_CLASS_KEY = "plan"
    HROM_CHARACTERISTICS_CLASS_KEY = "hrom_characteristics"
    PLAN_FILE_CLASS_PATTERN = re.compile(r"^UA\d{17}_plan$", re.IGNORECASE)
    HROM_CHARACTERISTICS_FILE_CLASS_PATTERN = re.compile(r"^UA\d{17}_hrom_characteristics$", re.IGNORECASE)
    SETTL_CHARACTERISTICS_CLASS_KEY = "settl_characteristics"
    SETTL_CHARACTERISTICS_FILE_CLASS_PATTERN = re.compile(r"^UA\d{17}_settl_characteristics$", re.IGNORECASE)
    INFO_CLASS_KEY = "info"
    INFO_FILE_CLASS_PATTERN = re.compile(r"^UA\d{17}_info$", re.IGNORECASE)
    INFO_STRICT_PROPERTIES = (
        "obj_guid",
        "name",
        "unit",
        "ind_in",
        "ind_pr",
        "ind_pro",
        "ind_ext",
        "note",
    )
    METADATA_STRICT_PROPERTIES = (
        "Title",
        "Doc_type",
        "Region",
        "Region_KOATUU",
        "Region_KATOTTH",
        "Hromada",
        "Hromada_KOATUU",
        "Hromada_KATOTTH",
        "Settlement",
        "Settl_KOATUU",
        "Settl_KATOTTH",
        "existing_term",
        "prime_term",
        "project_term",
        "Company_Name",
        "EDRPOU",
        "Address",
        "Phone",
        "Email",
        "Arch_LastName",
        "Arch_FirstName",
        "Arch_MiddleName",
        "Arch_Certificate_Number",
        "Arch_Certificate_Date",
        "Surv_Last_Name",
        "Surv_First_Name",
        "Surv_Middle_Name",
        "Surv_Certificate_Number",
        "Surv_Certificate_Date",
        "Decision_Authority",
        "Decision_Date",
        "Decision_Number",
        "Expertise_Authority",
        "Expertise_Date",
        "Expertise_Number",
        "Approval_Authority",
        "Approval_Date",
        "Approval_Number",
    )
    PLAN_STRICT_PROPERTIES = (
        "sol_num",
        "solution",
        "ind_name",
        "unit",
        "ind_in",
        "ind_pr",
        "ind_pro",
        "ind_ext",
        "note",
    )
    HROM_CHARACTERISTICS_STRICT_PROPERTIES = (
        "name",
        "unit",
        "ind_in",
        "ind_pr",
        "ind_pro",
        "ind_ext",
        "note",
    )
    SETTL_CHARACTERISTICS_PROPERTIES = (
        "name",
        "unit",
        "ind_in",
        "ind_pr",
        "ind_pro",
        "ind_ext",
        "note",
    )
    IGNORED_INTERNAL_PROPERTIES = {"fid"}
    YEAR_TERM_FIELDS = {"existing_term", "prime_term", "project_term"}
    YEAR_TERM_PATTERN = re.compile(r"^\d{4}$")

    def __init__(self, plugin):
        self.plugin = plugin

    def _is_four_digit_year_string(self, value) -> bool:
        if not isinstance(value, str):
            return False
        return bool(self.YEAR_TERM_PATTERN.fullmatch(value.strip()))

    def _schema_class_key(self, class_key: str) -> str:
        if not class_key:
            return class_key
        key_text = str(class_key).strip()
        key_lower = key_text.lower()
        if key_lower == self.PLAN_CLASS_KEY:
            return self.PLAN_CLASS_KEY
        if self.METADATA_FILE_CLASS_PATTERN.fullmatch(key_text) or key_lower.endswith(f"_{self.METADATA_CLASS_KEY}"):
            return self.METADATA_CLASS_KEY
        if self.PLAN_FILE_CLASS_PATTERN.fullmatch(key_text) or key_lower.endswith(f"_{self.PLAN_CLASS_KEY}"):
            return self.PLAN_CLASS_KEY
        if self.HROM_CHARACTERISTICS_FILE_CLASS_PATTERN.fullmatch(key_text) or key_lower.endswith(f"_{self.HROM_CHARACTERISTICS_CLASS_KEY}"):
            return self.HROM_CHARACTERISTICS_CLASS_KEY
        if self.SETTL_CHARACTERISTICS_FILE_CLASS_PATTERN.fullmatch(key_text) or key_lower.endswith(f"_{self.SETTL_CHARACTERISTICS_CLASS_KEY}"):
            return self.SETTL_CHARACTERISTICS_CLASS_KEY
        if self.INFO_FILE_CLASS_PATTERN.fullmatch(key_text) or key_lower.endswith(f"_{self.INFO_CLASS_KEY}"):
            return self.INFO_CLASS_KEY
        return class_key

    def _exclusive_profile_key(self, class_key: str) -> str:
        resolved = self._schema_class_key(class_key)
        if resolved in {
            self.METADATA_CLASS_KEY,
            self.PLAN_CLASS_KEY,
            self.HROM_CHARACTERISTICS_CLASS_KEY,
            self.SETTL_CHARACTERISTICS_CLASS_KEY,
            self.INFO_CLASS_KEY,
        }:
            return resolved
        return ""

    def _exclusive_props_tuple(self, profile_key: str):
        if profile_key == self.METADATA_CLASS_KEY:
            return self.METADATA_STRICT_PROPERTIES
        if profile_key == self.PLAN_CLASS_KEY:
            return self.PLAN_STRICT_PROPERTIES
        if profile_key == self.HROM_CHARACTERISTICS_CLASS_KEY:
            return self.HROM_CHARACTERISTICS_STRICT_PROPERTIES
        if profile_key == self.SETTL_CHARACTERISTICS_CLASS_KEY:
            return self.SETTL_CHARACTERISTICS_PROPERTIES
        if profile_key == self.INFO_CLASS_KEY:
            return self.INFO_STRICT_PROPERTIES
        return None

    def _is_internal_qgis_property(self, key: str) -> bool:
        if not key:
            return False
        normalized = self.plugin._normalize_cyrillic_key(str(key)).lower()
        return normalized in self.IGNORED_INTERNAL_PROPERTIES

    def allowed_props_for_class(self, class_key: str):
        if not class_key:
            return set()
        profile_key = self._exclusive_profile_key(class_key)
        exclusive_props = self._exclusive_props_tuple(profile_key)
        if exclusive_props is not None:
            return set(exclusive_props)
        class_key = self._schema_class_key(class_key)
        schema, _common_schema = self.plugin._load_schema_cache()
        props_schema = self.plugin._collect_properties_schema(class_key, schema)
        if not props_schema:
            return set()
        allowed = set()
        for name in props_schema.keys():
            normalized = self.plugin._normalize_cyrillic_key(name)
            if normalized.lower() in self.IGNORED_INTERNAL_PROPERTIES:
                continue
            allowed.add(normalized)
        return allowed

    def find_cyrillic_property_keys(self, data: dict, allowed_props: set) -> bool:
        if not isinstance(data, dict):
            return False
        features = None
        geo_type = data.get("type")
        if geo_type == "FeatureCollection":
            features = data.get("features")
        elif geo_type == "Feature":
            features = [data]
        if not isinstance(features, list):
            return False
        for feature in features:
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties")
            if not isinstance(props, dict):
                continue
            for key in props.keys():
                if self._is_internal_qgis_property(key):
                    continue
                normalized = self.plugin._normalize_cyrillic_key(key)
                if allowed_props and normalized not in allowed_props:
                    continue
                if normalized != key and any(ch in self.plugin._cyrillic_fix_map for ch in key):
                    return True
        return False

    def validate_geojson_file(
        self,
        source_path: str,
        class_key: str,
        project_dir: str,
        schema: dict,
        common_schema: dict,
        data: dict = None,
    ):
        errors = []
        error_entries = []
        if data is None:
            data = self.plugin._read_json_file(source_path)
        if not isinstance(data, dict):
            return ["Файл не є валідним JSON або не є об'єктом."], []
        geo_type = data.get("type")
        if geo_type == "FeatureCollection":
            features = data.get("features")
        elif geo_type == "Feature":
            features = [data]
        else:
            return [f"Невідомий тип GeoJSON: {geo_type!r}."], []
        if not isinstance(features, list):
            return ["Поле 'features' має бути масивом."], []
        schema_class_key = self._schema_class_key(class_key)
        profile_key = self._exclusive_profile_key(class_key)
        exclusive_props = self._exclusive_props_tuple(profile_key)
        props_schema = self.plugin._collect_properties_schema(class_key, schema)
        required_props = self.plugin._collect_required_properties_schema(class_key, schema, common_schema)
        if not props_schema:
            return [f"Схема для класу {class_key!r} не знайдена."], []
        normalized_props = {}
        for name, node in props_schema.items():
            normalized = self.plugin._normalize_cyrillic_key(name)
            if normalized.lower() in self.IGNORED_INTERNAL_PROPERTIES:
                continue
            if normalized not in normalized_props:
                normalized_props[normalized] = node
        allowed_props = set(normalized_props.keys())
        required_norm = set()
        required_map = {}
        for name in required_props:
            normalized = self.plugin._normalize_cyrillic_key(name)
            required_norm.add(normalized)
            if normalized not in required_map:
                required_map[normalized] = name
        if exclusive_props is not None:
            allowed_props = set(exclusive_props)
            required_norm = set(exclusive_props)
            required_map = {name: name for name in exclusive_props}
        if self.plugin._uses_state_change(class_key):
            allowed_props.update({"state", "change"})
        for index, feature in enumerate(features, start=1):
            feature_errors = []
            if not isinstance(feature, dict):
                message = f"[{index}] Feature не є об'єктом."
                errors.append(message)
                feature_errors.append(message)
                error_entries.append(
                    {
                        "layer": class_key,
                        "feature_index": index,
                        "feature_id": None,
                        "geometry": None,
                        "messages": feature_errors,
                    }
                )
                continue
            props = feature.get("properties")
            if not isinstance(props, dict):
                message = f"[{index}] Відсутній або некоректний 'properties'."
                errors.append(message)
                feature_errors.append(message)
                error_entries.append(
                    {
                        "layer": class_key,
                        "feature_index": index,
                        "feature_id": feature.get("id"),
                        "geometry": feature.get("geometry"),
                        "messages": feature_errors,
                    }
                )
                continue
            if schema_class_key == self.METADATA_CLASS_KEY:
                try:
                    props = self.plugin._normalize_metadata_properties(props)
                    feature["properties"] = props
                except Exception:
                    pass
            normalized_prop_keys = {self.plugin._normalize_cyrillic_key(k) for k in props.keys()}
            normalized_prop_keys = {k for k in normalized_prop_keys if k.lower() not in self.IGNORED_INTERNAL_PROPERTIES}
            for key in props.keys():
                if self._is_internal_qgis_property(key):
                    continue
                normalized_key = self.plugin._normalize_cyrillic_key(key)
                if normalized_key not in allowed_props:
                    message = f"[{index}] Невідоме поле '{key}'."
                    errors.append(message)
                    feature_errors.append(message)
            for key in required_norm:
                if key not in normalized_prop_keys:
                    name = required_map.get(key, key)
                    message = f"[{index}] Відсутнє обов'язкове поле '{name}'."
                    errors.append(message)
                    feature_errors.append(message)
            for key, value in props.items():
                normalized_key = self.plugin._normalize_cyrillic_key(key)
                if normalized_key.lower() in self.IGNORED_INTERNAL_PROPERTIES:
                    continue
                if normalized_key not in normalized_props:
                    if normalized_key in ("state", "change") and self.plugin._uses_state_change(class_key):
                        allowed_values = self.plugin._attributes_enum_keys(normalized_key)
                        if allowed_values is not None and value is not None:
                            value_key = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
                            if value_key not in allowed_values:
                                message = f"[{index}] Поле '{key}' має значення {value!r}, якого немає у списку enum."
                                errors.append(message)
                                feature_errors.append(message)
                    continue
                schema_node = normalized_props.get(normalized_key)
                schema_type = self.plugin._schema_simple_type(schema_node, schema, common_schema)
                if value is not None:
                    if schema_type == "integer" and not isinstance(value, int):
                        message = f"[{index}] Поле '{key}' має бути integer, але отримано {type(value).__name__}."
                        errors.append(message)
                        feature_errors.append(message)
                    elif schema_type == "number" and not isinstance(value, (int, float)):
                        message = f"[{index}] Поле '{key}' має бути number, але отримано {type(value).__name__}."
                        errors.append(message)
                        feature_errors.append(message)
                    elif schema_type == "boolean" and not isinstance(value, bool):
                        message = f"[{index}] Поле '{key}' має бути boolean, але отримано {type(value).__name__}."
                        errors.append(message)
                        feature_errors.append(message)
                    elif schema_type == "string" and not isinstance(value, str):
                        message = f"[{index}] Поле '{key}' має бути string, але отримано {type(value).__name__}."
                        errors.append(message)
                        feature_errors.append(message)
                    elif schema_type == "array" and not isinstance(value, list):
                        message = f"[{index}] Поле '{key}' має бути array, але отримано {type(value).__name__}."
                        errors.append(message)
                        feature_errors.append(message)
                    elif schema_type == "object" and not isinstance(value, dict):
                        message = f"[{index}] Поле '{key}' має бути object, але отримано {type(value).__name__}."
                        errors.append(message)
                        feature_errors.append(message)
                if value is not None and normalized_key in self.YEAR_TERM_FIELDS and not self._is_four_digit_year_string(value):
                    message = f"[{index}] Поле '{key}' має бути рядком у форматі РРРР."
                    errors.append(message)
                    feature_errors.append(message)
                enum_values = self.plugin._schema_enum_values(schema_node, schema, common_schema)
                if enum_values is not None and value is not None and value not in enum_values:
                    message = f"[{index}] Поле '{key}' має значення {value!r}, якого немає у списку enum."
                    errors.append(message)
                    feature_errors.append(message)
                if value is not None:
                    allowed_values = self.plugin._attributes_enum_keys(normalized_key)
                    if allowed_values is not None:
                        value_key = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
                        if value_key not in allowed_values:
                            message = f"[{index}] Поле '{key}' має значення {value!r}, якого немає у списку enum."
                            errors.append(message)
                            feature_errors.append(message)
            if feature_errors:
                feature_id = feature.get("id")
                if feature_id is None and isinstance(props, dict):
                    feature_id = props.get("id")
                error_entries.append(
                    {
                        "layer": class_key,
                        "feature_index": index,
                        "feature_id": feature_id,
                        "geometry": feature.get("geometry"),
                        "messages": feature_errors,
                    }
                )
        return errors, error_entries
