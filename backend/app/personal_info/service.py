from __future__ import annotations

from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlsplit

from backend.app.core.security import contains_secret
from backend.app.db.connection import connect
from backend.app.db.repository import new_id, now_iso


CATEGORIES = {
    "identity": "身份信息",
    "contact": "联系方式",
    "address": "地址信息",
    "work": "工作与实习",
    "education": "教育经历",
    "project": "项目经历",
    "skill": "技能",
    "certificate": "证书",
    "award": "获奖经历",
    "qa": "常用问答",
    "preference": "偏好设置",
    "other": "其他信息",
}

# Key, category, display label, aliases. Longer aliases win so “姓” does not
# accidentally consume “姓名”. autocomplete tokens are handled as aliases too.
FIELD_CATALOG: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "full_name": ("identity", "姓名", ("applicant name", "candidate name", "full name", "fullname", "name", "申请人姓名", "候选人姓名", "姓名", "真实姓名", "联系人")),
    "given_name": ("identity", "名", ("given name", "firstname", "first name", "名")),
    "family_name": ("identity", "姓", ("family name", "lastname", "last name", "surname", "姓")),
    "gender": ("identity", "性别", ("gender", "sex", "性别")),
    "birth_date": ("identity", "出生日期", ("bday", "birth date", "birthday", "date of birth", "出生日期", "生日")),
    "id_number": ("identity", "证件号码", ("id number", "identity number", "身份证", "证件号码")),
    "nationality": ("identity", "国籍", ("nationality", "citizenship", "国籍")),
    "email": ("contact", "邮箱", ("email", "e-mail", "email address", "邮箱", "电子邮箱")),
    "phone": ("contact", "手机号", ("tel", "telephone", "mobile", "phone", "phone number", "手机号", "手机", "联系电话", "电话")),
    "phone_country": ("contact", "手机国家/地区", ("tel-country-code", "calling code", "country code", "手机区号", "国家区号")),
    "website": ("contact", "个人网站", ("url", "website", "homepage", "个人网站", "主页")),
    "country": ("address", "国家/地区", ("country", "country-name", "国家", "地区")),
    "province": ("address", "省/州", ("address-level1", "state", "province", "省", "州")),
    "city": ("address", "城市", ("address-level2", "city", "城市", "市")),
    "district": ("address", "区/县", ("address-level3", "district", "区", "县")),
    "street_address": ("address", "详细地址", ("street-address", "address", "address line", "详细地址", "街道地址", "地址")),
    "postal_code": ("address", "邮政编码", ("postal-code", "zip", "zipcode", "postal code", "邮编", "邮政编码")),
    "company": ("work", "公司", ("organization", "company name", "company", "employer", "任职单位", "实习单位", "公司名称", "公司", "单位", "雇主")),
    "department": ("work", "部门", ("department name", "business unit", "department", "所在部门", "部门名称", "部门")),
    "job_title": ("work", "职位", ("organization-title", "job title", "position", "role title", "任职名称", "实习岗位", "岗位名称", "职位", "职务", "岗位")),
    "work_location": ("work", "工作地点", ("work location", "office location", "工作地点", "任职地点")),
    "work_start_date": ("work", "工作开始时间", ("employment start date", "work start date", "入职时间", "任职开始时间")),
    "work_end_date": ("work", "工作结束时间", ("employment end date", "work end date", "离职时间", "任职结束时间")),
    "work_description": ("work", "工作内容", ("work description", "responsibilities", "job description", "主要职责", "实习内容", "工作描述", "工作内容")),
    "work_results": ("work", "工作成果", ("work achievements", "achievements", "accomplishments", "工作业绩", "工作成果")),
    "recruitment_channel": ("work", "招聘渠道", ("recruitment channel", "application source", "招聘渠道", "获知职位渠道", "应聘渠道")),
    "school": ("education", "学校", ("school name", "school", "university", "学校名称", "学校", "大学", "院校")),
    "college": ("education", "学院", ("college name", "faculty", "department", "学院名称", "学院", "院系")),
    "degree": ("education", "学历/学位", ("highest degree", "degree", "education", "最高学位", "最高学历", "学历", "学位")),
    "major": ("education", "专业", ("major name", "major", "field of study", "专业名称", "专业")),
    "major_category": ("education", "专业类别", ("major category", "discipline", "专业类别", "学科门类")),
    "education_start_date": ("education", "教育开始时间", ("education start date", "school start date", "入学时间", "开始时间")),
    "education_end_date": ("education", "教育结束时间", ("education end date", "graduation date", "毕业时间", "结束时间")),
    "campus_experience": ("education", "在校经历", ("campus experience", "school experience", "在校经历", "校园经历")),
    "project_name": ("project", "项目名称", ("project title", "project name", "项目名称", "项目")),
    "project_role": ("project", "项目角色", ("project role", "role in project", "项目角色", "担任角色")),
    "project_start_date": ("project", "项目开始时间", ("project start date", "项目开始时间")),
    "project_end_date": ("project", "项目结束时间", ("project end date", "项目结束时间")),
    "project_background": ("project", "项目背景", ("project background", "项目背景")),
    "project_description": ("project", "项目介绍", ("project introduction", "project description", "项目介绍", "项目描述", "项目经历")),
    "project_work": ("project", "主要工作", ("project responsibilities", "main work", "主要工作", "项目职责")),
    "project_skills": ("project", "使用技能", ("technologies used", "tech stack", "skills used", "技术栈", "使用技能", "项目技能")),
    "project_results": ("project", "项目成果", ("project achievements", "project results", "项目成效", "项目成果")),
    "skill_name": ("skill", "技能名称", ("skill name", "skills", "professional skills", "技能名称", "专业技能", "技能")),
    "skill_level": ("skill", "熟练程度", ("proficiency", "skill level", "熟练程度", "掌握程度")),
    "certificate_name": ("certificate", "证书名称", ("certificate name", "certification", "qualification", "证书名称", "资格证书", "证书")),
    "certificate_issuer": ("certificate", "发证机构", ("issuing organization", "certificate issuer", "发证机构", "颁发机构")),
    "certificate_date": ("certificate", "获证时间", ("issue date", "certificate date", "获证时间", "发证日期")),
    "certificate_number": ("certificate", "证书编号", ("credential id", "certificate number", "证书编号")),
    "award_name": ("award", "奖项名称", ("award name", "honor", "奖项名称", "荣誉名称", "获奖名称")),
    "award_issuer": ("award", "授奖机构", ("award issuer", "awarding organization", "授奖机构", "颁奖机构")),
    "award_date": ("award", "获奖时间", ("award date", "获奖时间")),
    "award_description": ("award", "获奖说明", ("award description", "获奖说明", "奖项描述")),
    "self_introduction": ("qa", "自我介绍", ("self introduction", "personal introduction", "personal profile", "个人简介", "自我介绍")),
    "self_evaluation": ("qa", "自我评价", ("self evaluation", "self assessment", "自我评价")),
    "personal_strengths": ("qa", "个人优势", ("personal strengths", "strengths", "核心优势", "个人优势")),
    "leaving_reason": ("qa", "离职原因", ("reason for leaving", "leaving reason", "离职原因")),
    "career_plan": ("qa", "职业规划", ("career plan", "career goals", "职业目标", "职业规划")),
    "language": ("preference", "常用语言", ("language", "locale", "preferred language", "常用语言", "语言")),
}

RECORD_FIELD_ORDER = {
    key: index for index, key in enumerate((
        "school", "education_start_date", "education_end_date", "college",
        "major_category", "major", "degree", "campus_experience",
        "company", "department", "job_title", "work_location", "work_start_date",
        "work_end_date", "work_description", "work_results",
        "project_name", "project_role", "project_start_date", "project_end_date",
        "project_background", "project_description", "project_work", "project_skills", "project_results",
        "skill_name", "skill_level", "certificate_name", "certificate_issuer",
        "certificate_date", "certificate_number", "award_name", "award_issuer",
        "award_date", "award_description", "self_introduction", "self_evaluation",
        "personal_strengths", "leaving_reason", "career_plan",
    ))
}

RECORD_CATEGORIES = {"education", "work", "project", "skill", "certificate", "award", "qa"}
SENSITIVE_FIELD_KEYS = {"id_number", "birth_date", "gender"}
LONG_TEXT_FIELD_KEYS = {
    "campus_experience", "work_description", "work_results", "project_background",
    "project_description", "project_work", "project_results", "self_introduction",
    "self_evaluation", "personal_strengths", "leaving_reason", "career_plan",
}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.casefold())


def classify_field(field: dict[str, Any]) -> tuple[str | None, float]:
    autocomplete = str(field.get("autocomplete") or "").split()[-1:].pop() if str(field.get("autocomplete") or "").split() else ""
    parts = [autocomplete, str(field.get("label") or ""), str(field.get("name") or ""),
             str(field.get("placeholder") or ""), str(field.get("id") or ""),
             str(field.get("helper_text") or ""), str(field.get("context_text") or "")]
    haystacks = [_norm(part) for part in parts if part]
    best: tuple[str | None, float] = (None, 0.0)
    best_specificity = 0
    for key, (_category, _label, aliases) in FIELD_CATALOG.items():
        for alias in sorted(aliases, key=len, reverse=True):
            needle = _norm(alias)
            for index, haystack in enumerate(haystacks):
                if not needle or not haystack:
                    continue
                if needle == haystack:
                    score = 1.0 if index == 0 else 0.97
                elif len(needle) >= 2 and needle in haystack:
                    score = 0.91
                else:
                    score = SequenceMatcher(None, needle, haystack).ratio() * 0.82
                specificity = len(needle)
                if score > best[1] or (score == best[1] and specificity > best_specificity):
                    best = (key, score)
                    best_specificity = specificity
    return best if best[1] >= 0.68 else (None, best[1])


def list_fields(*, include_rejected: bool = False) -> list[dict[str, Any]]:
    where = "" if include_rejected else "WHERE status != 'rejected'"
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM personal_info_fields {where} ORDER BY category, label, updated_at DESC"
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["aliases"] = json.loads(item.pop("aliases_json") or "[]")
        result.append(item)
    return result


def get_field(field_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM personal_info_fields WHERE id=?", (field_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["aliases"] = json.loads(item.pop("aliases_json") or "[]")
    return item


def upsert_field(*, field_key: str, value: str, category: str | None = None,
                 label: str | None = None, aliases: list[str] | None = None,
                 source_type: str = "user_explicit", source_ref: str | None = None,
                 confidence: float = 1.0, status: str = "confirmed") -> dict[str, Any]:
    value = value.strip()
    if not value:
        raise ValueError("个人信息值不能为空")
    if contains_secret(value):
        raise ValueError("密钥或认证信息不能保存到个人信息库")
    if status not in {"proposed", "confirmed", "rejected"}:
        raise ValueError("无效的信息状态")
    catalog = FIELD_CATALOG.get(field_key)
    category = category or (catalog[0] if catalog else "other")
    label = label or (catalog[1] if catalog else field_key)
    if category not in CATEGORIES:
        raise ValueError("无效的个人信息分类")
    clean_aliases = list(dict.fromkeys(a.strip() for a in (aliases or []) if a.strip()))[:30]
    now = now_iso()
    with connect() as connection:
        existing = connection.execute("SELECT id, status, aliases_json FROM personal_info_fields WHERE field_key=?", (field_key,)).fetchone()
        if existing:
            field_id = str(existing["id"])
            # Low-confidence chat suggestions never overwrite confirmed data.
            if existing["status"] == "confirmed" and status == "proposed":
                return get_field(field_id) or {}
            previous_aliases = json.loads(existing["aliases_json"] or "[]")
            clean_aliases = list(dict.fromkeys([*previous_aliases, *clean_aliases]))[:30]
            connection.execute(
                """UPDATE personal_info_fields SET category=?, label=?, value=?, aliases_json=?,
                   source_type=?, source_ref=?, confidence=?, status=?, updated_at=? WHERE id=?""",
                (category, label, value, json.dumps(clean_aliases, ensure_ascii=False), source_type,
                 source_ref, max(0.0, min(confidence, 1.0)), status, now, field_id),
            )
        else:
            field_id = new_id()
            connection.execute(
                """INSERT INTO personal_info_fields
                   (id, category, field_key, label, value, aliases_json, source_type, source_ref,
                    confidence, status, sensitivity, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'personal', ?, ?)""",
                (field_id, category, field_key, label, value,
                 json.dumps(clean_aliases, ensure_ascii=False), source_type, source_ref,
                 max(0.0, min(confidence, 1.0)), status, now, now),
            )
    return get_field(field_id) or {}


def update_field(field_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    current = get_field(field_id)
    if not current:
        return None
    field_key = str(changes.get("field_key", current["field_key"]))
    if field_key != current["field_key"]:
        with connect() as connection:
            duplicate = connection.execute("SELECT id FROM personal_info_fields WHERE field_key=? AND id!=?", (field_key, field_id)).fetchone()
        if duplicate:
            raise ValueError("该字段键已存在")
    payload = {**current, **changes, "field_key": field_key}
    value = str(payload["value"]).strip()
    if not value or contains_secret(value):
        raise ValueError("个人信息值无效或包含认证秘密")
    if payload["category"] not in CATEGORIES or payload["status"] not in {"proposed", "confirmed", "rejected"}:
        raise ValueError("分类或状态无效")
    now = now_iso()
    with connect() as connection:
        connection.execute(
            """UPDATE personal_info_fields SET category=?, field_key=?, label=?, value=?, aliases_json=?,
               status=?, confidence=?, updated_at=? WHERE id=?""",
            (payload["category"], field_key, str(payload["label"]).strip() or field_key, value,
             json.dumps(payload.get("aliases") or [], ensure_ascii=False), payload["status"],
             float(payload.get("confidence", current["confidence"])), now, field_id),
        )
    return get_field(field_id)


def delete_field(field_id: str) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM personal_info_fields WHERE id=?", (field_id,))
    return cursor.rowcount > 0


def list_records(*, category: str | None = None) -> list[dict[str, Any]]:
    where = "WHERE r.status != 'rejected'"
    params: list[Any] = []
    if category:
        where += " AND r.category = ?"
        params.append(category)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT r.* FROM personal_info_records r {where} ORDER BY r.category, r.created_at, r.id",
            params,
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            fields = connection.execute(
                "SELECT * FROM personal_info_record_fields WHERE record_id=? ORDER BY created_at, id",
                (item["id"],),
            ).fetchall()
            item["fields"] = []
            for field_row in fields:
                record_field = dict(field_row)
                record_field["aliases"] = json.loads(record_field.pop("aliases_json") or "[]")
                item["fields"].append(record_field)
            item["fields"].sort(key=lambda field: (
                RECORD_FIELD_ORDER.get(str(field["field_key"]), len(RECORD_FIELD_ORDER)),
                str(field["field_key"]),
            ))
            result.append(item)
    return result


def _record_fingerprint(category: str, values: dict[str, str]) -> str:
    if category == "education":
        anchors = [values.get("school", ""), values.get("education_start_date", ""), values.get("degree", "")]
    elif category == "work":
        anchors = [values.get("company", ""), values.get("work_start_date", ""), values.get("job_title", "")]
    elif category == "project":
        anchors = [values.get("project_name", ""), values.get("project_start_date", ""), values.get("project_role", "")]
    elif category == "skill":
        anchors = [values.get("skill_name", ""), values.get("skill_level", "")]
    elif category == "certificate":
        anchors = [values.get("certificate_name", ""), values.get("certificate_issuer", ""), values.get("certificate_date", "")]
    elif category == "award":
        anchors = [values.get("award_name", ""), values.get("award_issuer", ""), values.get("award_date", "")]
    elif category == "qa":
        anchors = [f"{key}:{value}" for key, value in sorted(values.items())]
    else:
        anchors = [f"{key}:{value}" for key, value in sorted(values.items())]
    material = "|".join(_norm(value) for value in anchors if value)
    if not material:
        material = "|".join(f"{key}:{_norm(value)}" for key, value in sorted(values.items()))
    return hashlib.sha256(f"{category}|{material}".encode()).hexdigest()


def upsert_record(*, category: str, fields: list[dict[str, Any]], source_type: str,
                  source_ref: str | None, confidence: float = 1.0,
                  status: str = "confirmed") -> dict[str, Any]:
    if category not in RECORD_CATEGORIES:
        raise ValueError("无效的关联资料分类")
    if status not in {"proposed", "confirmed", "rejected"}:
        raise ValueError("无效的关联资料状态")
    clean_fields = [field for field in fields if str(field.get("value") or "").strip()]
    if not clean_fields:
        raise ValueError("关联记录不能是空的")
    values = {str(field["field_key"]): str(field["value"]).strip() for field in clean_fields}
    if any(contains_secret(value) for value in values.values()):
        raise ValueError("关联记录包含认证秘密")
    fingerprint = _record_fingerprint(category, values)
    primary_key = {
        "education": "school", "work": "company", "project": "project_name",
        "skill": "skill_name", "certificate": "certificate_name", "award": "award_name",
    }.get(category, "")
    label = values.get(primary_key) or next(iter(values.values()))
    now = now_iso()
    with connect() as connection:
        existing = connection.execute("SELECT id FROM personal_info_records WHERE fingerprint=?", (fingerprint,)).fetchone()
        if existing:
            record_id = str(existing["id"])
            connection.execute(
                """UPDATE personal_info_records SET label=?, source_type=?, source_ref=?, confidence=?,
                   status=?, updated_at=? WHERE id=?""",
                (label, source_type, source_ref, confidence, status, now, record_id),
            )
        else:
            record_id = new_id()
            connection.execute(
                """INSERT INTO personal_info_records
                   (id, category, record_type, label, fingerprint, source_type, source_ref,
                    confidence, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                 (record_id, category, f"{category}_record", label, fingerprint, source_type,
                 source_ref, confidence, status, now, now),
            )
        for field in clean_fields:
            field_key = str(field["field_key"])
            aliases = list(dict.fromkeys(str(alias).strip() for alias in field.get("aliases", []) if str(alias).strip()))[:30]
            previous = connection.execute(
                "SELECT aliases_json FROM personal_info_record_fields WHERE record_id=? AND field_key=?",
                (record_id, field_key),
            ).fetchone()
            if previous:
                aliases = list(dict.fromkeys([*json.loads(previous["aliases_json"] or "[]"), *aliases]))[:30]
            connection.execute(
                """INSERT INTO personal_info_record_fields
                   (id, record_id, field_key, label, value, aliases_json, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(record_id, field_key) DO UPDATE SET label=excluded.label,
                   value=excluded.value, aliases_json=excluded.aliases_json,
                   confidence=excluded.confidence, updated_at=excluded.updated_at""",
                (new_id(), record_id, field_key, str(field.get("label") or field_key),
                 str(field["value"]).strip(), json.dumps(aliases, ensure_ascii=False),
                 float(field.get("confidence") or confidence), now, now),
            )
    return next(item for item in list_records(category=category) if item["id"] == record_id)


def update_record_field(record_id: str, field_key: str, *, value: str, label: str | None = None) -> dict[str, Any] | None:
    value = value.strip()
    if not value or contains_secret(value):
        raise ValueError("关联字段值无效或包含认证秘密")
    now = now_iso()
    with connect() as connection:
        record = connection.execute("SELECT * FROM personal_info_records WHERE id=?", (record_id,)).fetchone()
        if not record:
            return None
        existing = connection.execute(
            "SELECT id, label FROM personal_info_record_fields WHERE record_id=? AND field_key=?",
            (record_id, field_key),
        ).fetchone()
        catalog = FIELD_CATALOG.get(field_key)
        field_label = label or (existing["label"] if existing else catalog[1] if catalog else field_key)
        if existing:
            connection.execute(
                "UPDATE personal_info_record_fields SET label=?, value=?, updated_at=? WHERE id=?",
                (field_label, value, now, existing["id"]),
            )
        else:
            connection.execute(
                """INSERT INTO personal_info_record_fields
                   (id, record_id, field_key, label, value, aliases_json, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, '[]', 1.0, ?, ?)""",
                (new_id(), record_id, field_key, field_label, value, now, now),
            )
        values = {row["field_key"]: row["value"] for row in connection.execute(
            "SELECT field_key, value FROM personal_info_record_fields WHERE record_id=?", (record_id,)
        ).fetchall()}
        fingerprint = _record_fingerprint(str(record["category"]), values)
        primary_key = {
            "education": "school", "work": "company", "project": "project_name",
            "skill": "skill_name", "certificate": "certificate_name", "award": "award_name",
        }.get(str(record["category"]), "")
        record_label = values.get(primary_key) or str(record["label"])
        connection.execute(
            "UPDATE personal_info_records SET label=?, fingerprint=?, source_type='user_edit', updated_at=? WHERE id=?",
            (record_label, fingerprint, now, record_id),
        )
    return next(item for item in list_records(category=str(record["category"])) if item["id"] == record_id)


def delete_record(record_id: str) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM personal_info_records WHERE id=?", (record_id,))
    return cursor.rowcount > 0


def delete_record_field(record_id: str, field_key: str) -> bool:
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM personal_info_record_fields WHERE record_id=? AND field_key=?",
            (record_id, field_key),
        )
        remaining = connection.execute(
            "SELECT COUNT(*) FROM personal_info_record_fields WHERE record_id=?", (record_id,)
        ).fetchone()[0]
        if cursor.rowcount and remaining == 0:
            connection.execute("DELETE FROM personal_info_records WHERE id=?", (record_id,))
    return cursor.rowcount > 0


def _section_category(field: dict[str, Any]) -> str | None:
    section = _norm(" ".join(str(field.get(name) or "") for name in ("section_title", "section_key")))
    if any(word in section for word in ("教育经历", "教育背景", "educationexperience", "educationhistory")):
        return "education"
    if any(word in section for word in ("项目经历", "项目经验", "projectexperience", "projects")):
        return "project"
    if any(word in section for word in ("工作经历", "实习经历", "workexperience", "employment", "internship")):
        return "work"
    if any(word in section for word in ("技能", "专业能力", "skills", "competencies")):
        return "skill"
    if any(word in section for word in ("证书", "资质", "certificates", "certifications")):
        return "certificate"
    if any(word in section for word in ("获奖", "荣誉", "奖项", "awards", "honors")):
        return "award"
    if any(word in section for word in ("开放题", "常用问答", "补充问题", "questions", "questionnaire")):
        return "qa"
    structural = _norm(" ".join(str(field.get(name) or "") for name in ("name", "id")))
    if any(word in structural for word in ("educationexperience", "educationhistory", "academichistory")):
        return "education"
    if any(word in structural for word in ("projectexperience", "projecthistory")):
        return "project"
    if any(word in structural for word in ("workexperience", "employmenthistory", "internshipexperience")):
        return "work"
    return None


def _key_for_category(key: str | None, category: str | None) -> str | None:
    if not key or not category:
        return key
    date_remaps = {
        ("education_start_date", "work"): "work_start_date",
        ("education_end_date", "work"): "work_end_date",
        ("education_start_date", "project"): "project_start_date",
        ("education_end_date", "project"): "project_end_date",
    }
    return date_remaps.get((key, category), key)


def _is_structured_field(category: str | None, section_category: str | None) -> bool:
    return bool(section_category in RECORD_CATEGORIES or category in {"project", "skill", "certificate", "award", "qa"})


def _parsed_field(field: dict[str, Any]) -> dict[str, Any] | None:
    if field.get("sensitive") or field.get("disabled") or field.get("readonly"):
        return None
    value = str(field.get("display_value") or field.get("value") or "").strip()
    if not value:
        return None
    key, score = classify_field(field)
    if key == "phone" and str(field.get("type") or "") == "custom_select":
        key = "phone_country"
    section_category = _section_category(field)
    catalog_category = FIELD_CATALOG.get(key, (None, "", ()))[0] if key else None
    category = section_category or catalog_category or "other"
    key = _key_for_category(key, category)
    if not key:
        raw = _norm(str(field.get("label") or field.get("name") or ""))[:48]
        if not raw:
            return None
        key, score = f"custom_{raw}", 0.62
    catalog = FIELD_CATALOG.get(key)
    structured = _is_structured_field(category, section_category)
    return {
        "field": field, "field_key": key, "value": value, "confidence": max(score, 0.72),
        "category": category, "structured": structured,
        "label": catalog[1] if catalog else str(field.get("label") or field.get("name") or key),
        "aliases": [str(field.get(name) or "") for name in ("label", "name", "placeholder", "autocomplete")],
    }


def _page_scope(page: dict[str, Any]) -> tuple[str, str]:
    parsed = urlsplit(str(page.get("url") or ""))
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    path = parsed.path or "/"
    dynamic_segment = re.compile(r"^(?:\d+|[0-9a-f]{8,}|[0-9a-f]{8}-[0-9a-f-]{20,})$", re.I)
    path_pattern = "/".join(":id" if dynamic_segment.fullmatch(segment) else segment
                            for segment in path.split("/"))
    return origin, path_pattern or "/"


def field_signature(field: dict[str, Any]) -> str:
    material = "|".join(_norm(str(field.get(name) or "")) for name in (
        "section_title", "label", "name", "placeholder", "autocomplete", "type",
    ))
    return hashlib.sha256(material.encode()).hexdigest()


def list_form_memories() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """SELECT m.*, f.label AS source_field_label, f.value AS source_field_value,
                      r.label AS source_record_label, r.category AS source_record_category
               FROM form_fill_memories m
               LEFT JOIN personal_info_fields f ON f.id=m.source_field_id
               LEFT JOIN personal_info_records r ON r.id=m.source_record_id
               ORDER BY m.updated_at DESC, m.id"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_form_memory(memory_id: str) -> dict[str, Any] | None:
    return next((item for item in list_form_memories() if item["id"] == memory_id), None)


def upsert_form_memory(
    *, page: dict[str, Any], field: dict[str, Any], field_key: str | None,
    action: str = "map", source_field_id: str | None = None,
    source_record_id: str | None = None, override_value: str | None = None,
) -> dict[str, Any]:
    if action not in {"map", "literal", "ignore", "defer"}:
        raise ValueError("无效的填写记忆动作")
    if override_value and contains_secret(override_value):
        raise ValueError("填写记忆不能包含认证秘密")
    origin, path_pattern = _page_scope(page)
    signature = field_signature(field)
    now = now_iso()
    with connect() as connection:
        existing = connection.execute(
            "SELECT id FROM form_fill_memories WHERE origin=? AND path_pattern=? AND field_signature=?",
            (origin, path_pattern, signature),
        ).fetchone()
        if existing:
            memory_id = str(existing["id"])
            connection.execute(
                """UPDATE form_fill_memories SET field_label=?, section_key=?, field_key=?, action=?,
                   source_field_id=?, source_record_id=?, override_value=?, updated_at=? WHERE id=?""",
                (str(field.get("label") or field.get("name") or ""), str(field.get("section_key") or ""),
                 field_key, action, source_field_id, source_record_id, override_value, now, memory_id),
            )
        else:
            memory_id = new_id()
            connection.execute(
                """INSERT INTO form_fill_memories
                   (id, origin, path_pattern, field_signature, field_label, section_key, field_key,
                    action, source_field_id, source_record_id, override_value, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory_id, origin, path_pattern, signature,
                 str(field.get("label") or field.get("name") or ""), str(field.get("section_key") or ""),
                 field_key, action, source_field_id, source_record_id, override_value, now, now),
            )
    return get_form_memory(memory_id) or {}


def update_form_memory(memory_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    current = get_form_memory(memory_id)
    if not current:
        return None
    allowed = {"field_key", "action", "source_field_id", "source_record_id", "override_value", "priority"}
    payload = {**current, **{key: value for key, value in changes.items() if key in allowed}}
    if payload["action"] not in {"map", "literal", "ignore", "defer"}:
        raise ValueError("无效的填写记忆动作")
    override = payload.get("override_value")
    if override and contains_secret(str(override)):
        raise ValueError("填写记忆不能包含认证秘密")
    priority = max(0, min(int(payload.get("priority") or 100), 1000))
    with connect() as connection:
        connection.execute(
            """UPDATE form_fill_memories SET field_key=?, action=?, source_field_id=?,
               source_record_id=?, override_value=?, priority=?, updated_at=? WHERE id=?""",
            (payload.get("field_key"), payload["action"], payload.get("source_field_id"),
             payload.get("source_record_id"), override, priority, now_iso(), memory_id),
        )
    return get_form_memory(memory_id)


def delete_form_memory(memory_id: str) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM form_fill_memories WHERE id=?", (memory_id,))
    return cursor.rowcount > 0


def _scope_memories(page: dict[str, Any]) -> dict[str, dict[str, Any]]:
    origin, path_pattern = _page_scope(page)
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM form_fill_memories WHERE origin=? AND path_pattern=? ORDER BY priority DESC, updated_at DESC",
            (origin, path_pattern),
        ).fetchall()
    return {str(row["field_signature"]): dict(row) for row in rows}


def remember_form(page: dict[str, Any]) -> dict[str, Any]:
    existing_fields = {item["field_key"]: item for item in list_fields(include_rejected=True)}
    existing_record_ids = {item["id"] for item in list_records()}
    learned: list[dict[str, Any]] = []
    learned_records: list[dict[str, Any]] = []
    template_fields: list[dict[str, str]] = []
    record_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw_field in page.get("fields") or []:
        parsed = _parsed_field(raw_field)
        if not parsed:
            continue
        key = str(parsed["field_key"])
        template_fields.append({"field_key": key, "label": str(raw_field.get("label") or ""),
                                "record_key": str(raw_field.get("record_key") or "")})
        if parsed["structured"]:
            if parsed["category"] == "qa" and not _section_category(raw_field):
                group_key = f"qa:{key}"
            else:
                group_key = str(raw_field.get("record_key") or f"{parsed['category']}:0")
            record_groups.setdefault((str(parsed["category"]), group_key), []).append(parsed)
            continue
        saved = upsert_field(
            field_key=key, value=str(parsed["value"]), category=str(parsed["category"]),
            label=str(parsed["label"]), aliases=list(parsed["aliases"]), source_type="form_capture",
            source_ref=str(page.get("url") or ""), confidence=max(float(parsed["confidence"]), 0.8),
            status="confirmed",
        )
        learned.append(saved)
        upsert_form_memory(page=page, field=raw_field, field_key=key, source_field_id=str(saved["id"]))
    for (category, _group_key), fields in record_groups.items():
        saved_record = upsert_record(
            category=category,
            fields=[{"field_key": field["field_key"], "label": field["label"], "value": field["value"],
                     "aliases": field["aliases"], "confidence": field["confidence"]} for field in fields],
            source_type="form_capture", source_ref=str(page.get("url") or ""),
            confidence=min(float(field["confidence"]) for field in fields), status="confirmed",
        )
        learned_records.append(saved_record)
        for parsed in fields:
            upsert_form_memory(
                page=page, field=parsed["field"], field_key=str(parsed["field_key"]),
                source_record_id=str(saved_record["id"]),
            )
    url = urlsplit(str(page.get("url") or ""))
    signature_source = "|".join(sorted(item["field_key"] for item in template_fields))
    signature = hashlib.sha256(f"{url.netloc}|{url.path}|{signature_source}".encode()).hexdigest()
    now = now_iso()
    with connect() as connection:
        existing = connection.execute("SELECT id FROM form_templates WHERE signature=?", (signature,)).fetchone()
        if existing:
            template_id = str(existing["id"])
            connection.execute("UPDATE form_templates SET title=?, fields_json=?, updated_at=? WHERE id=?",
                               (str(page.get("title") or ""), json.dumps(template_fields, ensure_ascii=False), now, template_id))
        else:
            template_id = new_id()
            connection.execute("""INSERT INTO form_templates
                (id, origin, path_pattern, title, signature, fields_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (template_id, f"{url.scheme}://{url.netloc}", url.path, str(page.get("title") or ""),
                 signature, json.dumps(template_fields, ensure_ascii=False), now, now))
    learned_count = len(learned) + sum(len(record["fields"]) for record in learned_records)
    unique_fields = {item["field_key"]: item for item in learned}
    created_count = sum(key not in existing_fields for key in unique_fields)
    merged_count = len(unique_fields) - created_count
    for record in learned_records:
        record_field_count = len(record["fields"])
        if record["id"] in existing_record_ids:
            merged_count += record_field_count
        else:
            created_count += record_field_count
    saved_count = created_count + merged_count
    return {"template_id": template_id, "learned": learned, "records": learned_records,
            "learned_count": learned_count,
            "recognized_count": learned_count, "saved_count": saved_count,
            "created_count": created_count, "merged_count": merged_count,
            "skipped_count": max(0, len(page.get("fields") or []) - learned_count)}


def match_form(page: dict[str, Any]) -> dict[str, Any]:
    stored = {item["field_key"]: item for item in list_fields() if item["status"] == "confirmed"}
    records_by_category = {category: list_records(category=category) for category in RECORD_CATEGORIES}
    assignments, unmatched = [], []
    structured_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for field in page.get("fields") or []:
        if field.get("sensitive") or field.get("disabled") or field.get("readonly"):
            continue
        key, score = classify_field(field)
        if key == "phone" and str(field.get("type") or "") == "custom_select":
            key = "phone_country"
        section_category = _section_category(field)
        catalog_category = FIELD_CATALOG.get(key, (None, "", ()))[0] if key else None
        category = section_category or catalog_category
        key = _key_for_category(key, category)
        if _is_structured_field(category, section_category):
            if category == "qa" and not section_category:
                group_key = f"qa:{key or field_signature(field)}"
            else:
                group_key = str(field.get("record_key") or f"{category}:0")
            structured_groups.setdefault((category, group_key), []).append({"field": field, "key": key, "score": score})
            continue
        item = stored.get(key or "")
        if not item and key is None:
            # User-created aliases allow the library to grow beyond the built-in catalog.
            probe = _norm(" ".join(str(field.get(k) or "") for k in ("label", "name", "placeholder")))
            for candidate in stored.values():
                alias_score = max((SequenceMatcher(None, _norm(alias), probe).ratio() for alias in candidate["aliases"] if alias), default=0.0)
                if alias_score >= 0.72:
                    item, score = candidate, alias_score
                    break
        if item:
            assignments.append({"field_id": field["field_id"], "field_key": item["field_key"],
                                "label": field.get("label") or item["label"], "value": item["value"],
                                "confidence": round(min(float(item["confidence"]), max(score, 0.7)), 3),
                                "source_id": item["id"]})
        else:
            unmatched.append({"field_id": field.get("field_id"), "label": field.get("label") or field.get("name") or "未命名字段"})
    for (category, group_key), group_fields in structured_groups.items():
        records = records_by_category.get(category) or []
        requested_keys = {str(item["key"]) for item in group_fields if item.get("key")}
        if requested_keys:
            records = [record for record in records if requested_keys.intersection(
                str(record_field["field_key"]) for record_field in record.get("fields", [])
            )]
        record_index = min((int(item["field"].get("record_index") or 0) for item in group_fields), default=0)
        record = records[record_index] if record_index < len(records) else None
        record_values = {item["field_key"]: item for item in (record or {}).get("fields", [])}
        for group_field in group_fields:
            field, key, score = group_field["field"], group_field["key"], group_field["score"]
            if not key:
                raw = _norm(str(field.get("label") or field.get("name") or ""))[:48]
                key = f"custom_{raw}" if raw else None
            item = record_values.get(key or "")
            if not item:
                probe = _norm(" ".join(str(field.get(name) or "") for name in ("label", "name", "placeholder")))
                for candidate in record_values.values():
                    alias_score = max((SequenceMatcher(None, _norm(alias), probe).ratio()
                                       for alias in candidate.get("aliases", []) if alias), default=0.0)
                    if alias_score >= 0.72:
                        item, score = candidate, alias_score
                        break
            if item:
                assignments.append({"field_id": field["field_id"], "field_key": item["field_key"],
                                    "label": field.get("label") or item["label"], "value": item["value"],
                                    "confidence": round(min(float(item["confidence"]), max(score, 0.7)), 3),
                                    "source_id": item["id"], "record_id": record["id"], "record_key": group_key})
            else:
                unmatched.append({"field_id": field.get("field_id"), "label": field.get("label") or field.get("name") or "未命名字段",
                                  "record_key": group_key})
    return {"assignments": assignments, "unmatched": unmatched}


def _field_memory_shape(field: dict[str, Any]) -> dict[str, Any]:
    return {name: field.get(name) for name in (
        "section_title", "section_key", "label", "name", "placeholder", "autocomplete", "type",
    )}


def _record_candidate(record: dict[str, Any], field_key: str) -> dict[str, Any] | None:
    item = next((value for value in record.get("fields", []) if value["field_key"] == field_key), None)
    if not item:
        return None
    return {
        "source_id": item["id"], "record_id": record["id"], "record_label": record["label"],
        "label": item["label"], "value": item["value"], "source_type": "record",
    }


def _scalar_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": item["id"], "record_id": None, "record_label": None,
        "label": item["label"], "value": item["value"], "source_type": "field",
    }


def _status_for_candidate(
    field: dict[str, Any], *, field_key: str | None, confidence: float,
    value: str, remembered: bool,
) -> tuple[str, str]:
    current_value = str(field.get("display_value") or field.get("value") or "").strip()
    if current_value:
        return "existing", "网页字段已有内容，需明确选择替换"
    control_type = str(field.get("type") or "").lower()
    choice_control = control_type in {"select", "custom_select", "radio", "custom_radio", "checkbox"}
    long_text = control_type == "textarea" or field_key in LONG_TEXT_FIELD_KEYS or len(value) > 160
    if field_key in SENSITIVE_FIELD_KEYS:
        return "confirm", "敏感个人信息需确认"
    if choice_control:
        return "confirm", "选择类控件需确认"
    if long_text:
        return "confirm", "长文本需确认或调整"
    if confidence < 0.82 and not remembered:
        return "confirm", "字段含义置信度较低，需确认"
    return "ready", "唯一且高置信度，可安全填写"


def _alias_scalar_candidate(field: dict[str, Any], stored: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    probe = _norm(" ".join(str(field.get(name) or "") for name in (
        "label", "name", "placeholder", "helper_text", "context_text",
    )))
    best_item, best_score = None, 0.0
    for candidate in stored:
        aliases = [candidate.get("label", ""), candidate.get("field_key", ""), *(candidate.get("aliases") or [])]
        score = max((SequenceMatcher(None, _norm(str(alias)), probe).ratio() for alias in aliases if alias), default=0.0)
        if score > best_score:
            best_item, best_score = candidate, score
    return (best_item, best_score) if best_score >= 0.72 else (None, best_score)


def build_form_plan(page: dict[str, Any]) -> dict[str, Any]:
    scalar_items = [item for item in list_fields() if item["status"] == "confirmed"]
    scalar_by_key = {str(item["field_key"]): item for item in scalar_items}
    scalar_by_id = {str(item["id"]): item for item in scalar_items}
    records = [item for item in list_records() if item["status"] == "confirmed"]
    records_by_category = {category: [item for item in records if item["category"] == category]
                           for category in RECORD_CATEGORIES}
    records_by_id = {str(item["id"]): item for item in records}
    memories = _scope_memories(page)
    planned_fields: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for raw in page.get("fields") or []:
        if raw.get("sensitive") or raw.get("disabled") or raw.get("readonly"):
            continue
        key, score = classify_field(raw)
        section_category = _section_category(raw)
        catalog_category = FIELD_CATALOG.get(key, (None, "", ()))[0] if key else None
        category = section_category or catalog_category or "other"
        key = _key_for_category(key, category)
        signature = field_signature(raw)
        memory = memories.get(signature)
        base = {
            "field_id": str(raw.get("field_id") or ""),
            "signature": signature,
            "field_key": key,
            "category": category,
            "structured": _is_structured_field(category, section_category),
            "label": str(raw.get("label") or raw.get("name") or "未命名字段"),
            "section_title": str(raw.get("section_title") or ""),
            "section_key": str(raw.get("section_key") or ""),
            "record_key": str(raw.get("record_key") or ""),
            "record_index": int(raw.get("record_index") or 0),
            "control_type": str(raw.get("type") or "text"),
            "current_value": str(raw.get("display_value") or raw.get("value") or "").strip(),
            "confidence": round(float(score), 3),
            "required": bool(raw.get("required")),
            "memory_id": str(memory["id"]) if memory else None,
            "memory_field": _field_memory_shape(raw),
        }
        if memory and memory["action"] in {"ignore", "defer"}:
            planned_fields.append({**base, "status": memory["action"], "reason": "已应用用户确认的站点记忆",
                                   "candidates": [], "selected": None})
            continue
        if _is_structured_field(category, section_category):
            if category == "qa" and not section_category:
                group_key = f"qa:{key or signature}"
            else:
                group_key = str(raw.get("record_key") or f"{category}:0")
            grouped.setdefault((category, group_key), []).append({"raw": raw, "base": base, "memory": memory})
            continue

        candidate = None
        remembered = False
        if memory and memory.get("action") == "literal" and memory.get("override_value") is not None:
            candidate = {
                "source_id": memory["id"], "record_id": None, "record_label": None,
                "label": base["label"], "value": str(memory["override_value"]), "source_type": "literal",
            }
            remembered = True
        elif memory and memory.get("source_field_id") in scalar_by_id:
            candidate = _scalar_candidate(scalar_by_id[str(memory["source_field_id"])])
            remembered = True
        elif key and key in scalar_by_key:
            candidate = _scalar_candidate(scalar_by_key[key])
        else:
            alias_item, alias_score = _alias_scalar_candidate(raw, scalar_items)
            if alias_item:
                candidate, score = _scalar_candidate(alias_item), alias_score
                base["field_key"] = alias_item["field_key"]
                base["category"] = alias_item["category"]
                base["confidence"] = round(alias_score, 3)
        if not candidate:
            planned_fields.append({**base, "status": "missing", "reason": "个人资料库中没有对应信息",
                                   "candidates": [], "selected": None})
            continue
        status, reason = _status_for_candidate(raw, field_key=base["field_key"],
                                                confidence=float(base["confidence"]),
                                                value=str(candidate["value"]), remembered=remembered)
        planned_fields.append({**base, "status": status, "reason": reason,
                               "candidates": [candidate], "selected": candidate})

    groups: list[dict[str, Any]] = []
    for (category, group_key), entries in grouped.items():
        requested_keys = {str(entry["base"]["field_key"]) for entry in entries if entry["base"].get("field_key")}
        candidates = [record for record in records_by_category.get(category, []) if requested_keys.intersection(
            str(value["field_key"]) for value in record.get("fields", [])
        )]
        remembered_ids = {
            str(entry["memory"]["source_record_id"]) for entry in entries
            if entry["memory"] and entry["memory"].get("source_record_id") in records_by_id
        }
        selected_record = records_by_id[next(iter(remembered_ids))] if len(remembered_ids) == 1 else candidates[0] if len(candidates) == 1 else None
        group_candidates = [{
            "record_id": record["id"], "label": record["label"], "category": record["category"],
            "source_type": record["source_type"],
            "fields": {value["field_key"]: value["value"] for value in record.get("fields", [])},
        } for record in candidates]
        group_status = "ready" if selected_record else "choose" if candidates else "missing"
        groups.append({"group_key": group_key, "category": category, "status": group_status,
                       "selected_record_id": selected_record["id"] if selected_record else None,
                       "remembered": bool(selected_record and remembered_ids), "candidates": group_candidates})
        for entry in entries:
            raw, base = entry["raw"], entry["base"]
            key = str(base.get("field_key") or "")
            field_candidates = [candidate for record in candidates if (candidate := _record_candidate(record, key))]
            if not candidates or not field_candidates:
                planned_fields.append({**base, "record_key": group_key, "status": "missing",
                                       "reason": "所选资料类型中没有对应字段", "candidates": [], "selected": None})
                continue
            if not selected_record:
                planned_fields.append({**base, "record_key": group_key, "status": "choose",
                                       "reason": "存在多条候选资料，请先选择整条记录",
                                       "candidates": field_candidates, "selected": None})
                continue
            selected = _record_candidate(selected_record, key)
            if not selected:
                planned_fields.append({**base, "record_key": group_key, "status": "missing",
                                       "reason": "选定记录缺少该字段", "candidates": field_candidates, "selected": None})
                continue
            status, reason = _status_for_candidate(raw, field_key=key, confidence=float(base["confidence"]),
                                                    value=str(selected["value"]), remembered=bool(remembered_ids))
            planned_fields.append({**base, "record_key": group_key, "status": status, "reason": reason,
                                   "candidates": field_candidates, "selected": selected})

    auto_assignments = [{
        "field_id": item["field_id"], "field_key": item.get("field_key"),
        "value": item["selected"]["value"], "source_id": item["selected"]["source_id"],
        "record_id": item["selected"].get("record_id"), "allow_overwrite": False,
        "expected_current_value": "",
    } for item in planned_fields if item["status"] == "ready" and item.get("selected")]
    counts = {status: sum(item["status"] == status for item in planned_fields) for status in (
        "ready", "choose", "confirm", "existing", "missing", "ignore", "defer",
    )}
    return {
        "target": {"url": str(page.get("url") or ""), "tab": page.get("tab_id"),
                   "document_id": page.get("document_id")},
        "title": str(page.get("title") or ""), "fields": planned_fields, "groups": groups,
        "auto_assignments": auto_assignments, "summary": counts, "submitted": False,
    }


def create_form_session(page: dict[str, Any]) -> dict[str, Any]:
    plan = build_form_plan(page)
    session_id = new_id()
    plan["session_id"] = session_id
    now = datetime.now(UTC)
    origin, path_pattern = _page_scope(page)
    with connect() as connection:
        connection.execute("DELETE FROM form_fill_sessions WHERE expires_at < ?", (now.isoformat(),))
        connection.execute(
            """INSERT INTO form_fill_sessions
               (id, origin, path_pattern, url, title, tab_id, document_id, plan_json, status,
                expires_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (session_id, origin, path_pattern, str(page.get("url") or ""), str(page.get("title") or ""),
             str(page.get("tab_id")) if page.get("tab_id") is not None else None,
             str(page.get("document_id")) if page.get("document_id") is not None else None,
             json.dumps(plan, ensure_ascii=False), (now + timedelta(minutes=30)).isoformat(),
             now.isoformat(), now.isoformat()),
        )
    return plan


def get_form_session(session_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM form_fill_sessions WHERE id=?", (session_id,)).fetchone()
    if not row or str(row["expires_at"]) < datetime.now(UTC).isoformat():
        return None
    result = dict(row)
    result["plan"] = json.loads(result.pop("plan_json"))
    return result


def mark_form_session_filled(
    session_id: str, field_ids: list[str], *, status: str = "pending",
    resolved_actions: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    session = get_form_session(session_id)
    if not session:
        return None
    filled = set(field_ids)
    resolved_actions = resolved_actions or {}
    for item in session["plan"]["fields"]:
        if item["field_id"] in filled:
            item["status"] = "filled"
            item["reason"] = "已安全自动填写；表单未提交"
        elif item["field_id"] in resolved_actions:
            item["status"] = resolved_actions[item["field_id"]]
            item["reason"] = "已按本次选择处理"
    statuses = ("ready", "choose", "confirm", "existing", "missing", "ignore", "defer", "filled")
    session["plan"]["summary"] = {
        item_status: sum(item["status"] == item_status for item in session["plan"]["fields"])
        for item_status in statuses
    }
    with connect() as connection:
        connection.execute("UPDATE form_fill_sessions SET plan_json=?, status=?, updated_at=? WHERE id=?",
                           (json.dumps(session["plan"], ensure_ascii=False), status, now_iso(), session_id))
    return session["plan"]


def resolve_form_session(session_id: str, choices: dict[str, Any]) -> dict[str, Any]:
    session = get_form_session(session_id)
    if not session:
        raise ValueError("填写会话不存在或已过期，请重新识别表单")
    if session["status"] not in {"pending", "partial"}:
        raise ValueError("填写会话已经完成")
    group_choices = {str(key): str(value) for key, value in (choices.get("groups") or {}).items() if value}
    field_choices = choices.get("fields") or {}
    apply_ready = bool(choices.get("apply_ready", True))
    assignments, resolutions = [], []
    for item in session["plan"]["fields"]:
        field_id = str(item["field_id"])
        instruction = field_choices.get(field_id) or {}
        action = str(instruction.get("action") or "")
        if action == "skip":
            continue
        if action in {"ignore", "defer"}:
            resolutions.append({"field": item, "action": action, "remember": bool(instruction.get("remember", choices.get("remember")))})
            continue
        if item["status"] in {"filled", "ignore", "defer"}:
            continue
        selected = item.get("selected")
        if item["status"] == "choose":
            record_id = group_choices.get(str(item.get("record_key") or ""))
            selected = next((candidate for candidate in item.get("candidates", []) if str(candidate.get("record_id")) == record_id), None)
            if not selected:
                continue
        explicit_fill = action == "fill"
        if item["status"] == "ready" and not apply_ready and not explicit_fill:
            continue
        if item["status"] in {"confirm", "existing", "missing"} and not explicit_fill:
            continue
        if item["status"] == "choose" and not group_choices.get(str(item.get("record_key") or "")):
            continue
        proposed_value = str(instruction.get("value") if instruction.get("value") is not None
                             else (selected or {}).get("value") or "").strip()
        if not proposed_value or contains_secret(proposed_value):
            continue
        replace_existing = bool(instruction.get("replace_existing"))
        if item.get("current_value") and not replace_existing:
            continue
        assignments.append({
            "field_id": field_id, "field_key": item.get("field_key"), "value": proposed_value,
            "source_id": (selected or {}).get("source_id"), "record_id": (selected or {}).get("record_id"),
            "allow_overwrite": replace_existing,
            "expected_current_value": str(item.get("current_value") or ""),
        })
        resolutions.append({
            "field": item, "action": "fill", "value": proposed_value, "selected": selected,
            "remember": bool(instruction.get("remember", choices.get("remember"))),
            "save_to_profile": bool(instruction.get("save_to_profile")),
        })
    return {"session": session, "assignments": assignments, "resolutions": resolutions}


def finalize_form_session(
    session_id: str, resolutions: list[dict[str, Any]], filled_field_ids: list[str],
) -> dict[str, Any]:
    session = get_form_session(session_id)
    if not session:
        raise ValueError("填写会话不存在或已过期")
    filled = set(filled_field_ids)
    page = {"url": session["url"]}
    for resolution in resolutions:
        item = resolution["field"]
        field_id = str(item["field_id"])
        action = resolution["action"]
        if action == "fill" and field_id not in filled:
            continue
        if resolution.get("save_to_profile") and action == "fill":
            key = str(item.get("field_key") or f"custom_{item['signature'][:12]}")
            category = str(item.get("category") or "other")
            if item.get("structured") and category in RECORD_CATEGORIES:
                saved_record = upsert_record(category=category, fields=[{
                    "field_key": key, "label": item["label"], "value": resolution["value"],
                    "aliases": [item["label"]], "confidence": 1.0,
                }], source_type="user_edit", source_ref=session["url"])
                resolution["selected"] = {"source_id": None, "record_id": saved_record["id"], "value": resolution["value"]}
            else:
                saved = upsert_field(field_key=key, value=resolution["value"], category=category,
                                     label=item["label"], aliases=[item["label"]], source_type="user_edit")
                resolution["selected"] = {"source_id": saved["id"], "record_id": None, "value": resolution["value"]}
        if resolution.get("remember"):
            selected = resolution.get("selected") or {}
            remembered_action = action
            override = None
            if action == "fill":
                candidate_value = str(selected.get("value") or "")
                changed = resolution.get("value") != candidate_value
                remembered_action = "literal" if changed or not (selected.get("source_id") or selected.get("record_id")) else "map"
                override = resolution.get("value") if remembered_action == "literal" else None
            memory = upsert_form_memory(
                page=page, field=item["memory_field"], field_key=item.get("field_key"), action=remembered_action,
                source_field_id=selected.get("source_id") if selected.get("source_type") != "record" else None,
                source_record_id=selected.get("record_id"), override_value=override,
            )
            with connect() as connection:
                connection.execute("UPDATE form_fill_memories SET use_count=use_count+1, last_used_at=? WHERE id=?",
                                   (now_iso(), memory["id"]))
    resolved_actions = {str(item["field"]["field_id"]): str(item["action"])
                        for item in resolutions if item["action"] in {"ignore", "defer"}}
    plan = mark_form_session_filled(session_id, list(filled), status="partial",
                                    resolved_actions=resolved_actions) or session["plan"]
    terminal = {"filled", "ignore", "defer"}
    complete = all(item["status"] in terminal for item in plan["fields"])
    if complete:
        with connect() as connection:
            connection.execute("UPDATE form_fill_sessions SET status='completed', updated_at=? WHERE id=?",
                               (now_iso(), session_id))
    return plan


CHAT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"(?:我的)?(?:邮箱|电子邮箱)(?:是|为|：|:)?\s*([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})", re.I)),
    ("phone", re.compile(r"(?:我的)?(?:手机号|手机|联系电话)(?:是|为|：|:)?\s*(1[3-9]\d{9})")),
    ("full_name", re.compile(r"(?:我叫|我的姓名(?:是|为|：|:))\s*([\u4e00-\u9fff·]{2,20})")),
    ("company", re.compile(r"(?:我在|我的公司(?:是|为|：|:))\s*([^，。,.]{2,40})(?:工作|任职)?")),
    ("job_title", re.compile(r"(?:我的职位(?:是|为|：|:)|我是(?:一名)?)\s*([^，。,.]{2,30})")),
    ("school", re.compile(r"(?:我毕业于|我的学校(?:是|为|：|:))\s*([^，。,.]{2,40})")),
)


def learn_from_chat(message: str, *, source_ref: str | None, explicit: bool) -> list[dict[str, Any]]:
    learned = []
    for key, pattern in CHAT_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        learned.append(upsert_field(field_key=key, value=match.group(1).strip(), source_type="user_explicit" if explicit else "chat_inferred",
                                    source_ref=source_ref, confidence=1.0 if explicit else 0.82,
                                    status="confirmed" if explicit else "proposed"))
    return learned
