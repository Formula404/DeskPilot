from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.db.connection import connect, init_db
from backend.app.main import app
from backend.app.agent.intents import legacy_rule_fallback
from backend.app.agent.specialists.web_agent import WebAgent
from backend.app.tools.browser.form_autofill import _session_reference
from backend.app.personal_info.service import (
    build_form_plan,
    classify_field,
    create_form_session,
    finalize_form_session,
    learn_from_chat,
    list_fields,
    list_form_memories,
    list_records,
    match_form,
    remember_form,
    resolve_form_session,
    upsert_field,
    upsert_record,
)


@pytest.fixture
def personal_data_dir(tmp_path):
    settings = get_settings()
    original = settings.data_dir
    settings.data_dir = tmp_path / "data"
    init_db()
    try:
        yield settings.data_dir
    finally:
        settings.data_dir = original


def field(field_id: str, *, label: str, value: str = "", name: str = "", autocomplete: str = "", field_type: str = "text", **extra) -> dict:
    return {
        "field_id": field_id, "label": label, "value": value, "name": name,
        "autocomplete": autocomplete, "placeholder": "", "id": "", "type": field_type,
        "sensitive": False, "disabled": False, "readonly": False, **extra,
    }


def test_field_semantics_use_autocomplete_and_multilingual_labels(personal_data_dir) -> None:
    assert classify_field(field("dp-field-0", label="Contact", autocomplete="email"))[0] == "email"
    assert classify_field(field("dp-field-1", label="联系电话"))[0] == "phone"
    assert classify_field(field("dp-field-2", label="邮政编码"))[0] == "postal_code"
    assert classify_field(field("dp-field-3", label="获得此职位招聘渠道（选择一个填写）"))[0] == "recruitment_channel"


def test_remember_and_match_similar_form_without_sensitive_values(personal_data_dir) -> None:
    captured = {
        "url": "https://jobs.example/apply/42", "title": "Apply", "fields": [
            field("dp-field-0", label="电子邮箱", value="alice@example.com"),
            field("dp-field-1", label="手机号码", value="13800138000"),
            {**field("dp-field-2", label="密码", value="do-not-store", field_type="password"), "sensitive": True},
        ],
    }
    result = remember_form(captured)
    assert len(result["learned"]) == 2
    assert {item["field_key"] for item in list_fields()} == {"email", "phone"}
    with connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM form_templates").fetchone()[0] == 1

    similar = {"url": "https://other.example/profile", "fields": [
        field("dp-field-9", label="Email address", name="contact_email"),
        field("dp-field-10", label="联系电话"),
        {**field("dp-field-11", label="Password", field_type="password"), "sensitive": True},
    ]}
    matches = match_form(similar)
    assert {(item["field_id"], item["value"]) for item in matches["assignments"]} == {
        ("dp-field-9", "alice@example.com"), ("dp-field-10", "13800138000")
    }


def test_remember_reports_recognized_controls_separately_from_unique_saved_fields(personal_data_dir) -> None:
    upsert_field(field_key="phone", value="13800138000", status="confirmed")
    result = remember_form({"url": "https://jobs.example/apply", "fields": [
        field("phone-native", label="手机号码", value="13900139000"),
        field("phone-widget", label="手机号码", value="13900139000", field_type="custom_input"),
        field("email", label="邮箱", value="alice@example.com"),
    ]})

    assert result["recognized_count"] == 3
    assert result["saved_count"] == 2
    assert result["created_count"] == 1
    assert result["merged_count"] == 1
    assert {item["field_key"] for item in list_fields()} == {"phone", "email"}


def test_chat_growth_is_proposed_and_cannot_overwrite_confirmed_data(personal_data_dir) -> None:
    proposed = learn_from_chat("我的邮箱是 new@example.com", source_ref="task-1", explicit=False)
    assert proposed[0]["status"] == "proposed"
    upsert_field(field_key="email", value="confirmed@example.com", status="confirmed")
    learn_from_chat("我的邮箱是 accidental@example.com", source_ref="task-2", explicit=False)
    stored = list_fields()[0]
    assert stored["value"] == "confirmed@example.com"
    assert stored["status"] == "confirmed"


def test_personal_info_api_supports_create_edit_confirm_and_delete(personal_data_dir) -> None:
    client = TestClient(app)
    created = client.post("/personal-info", json={
        "category": "contact", "field_key": "backup_email", "label": "备用邮箱",
        "value": "backup@example.com", "aliases": ["alternate email"],
    })
    assert created.status_code == 201
    field_id = created.json()["id"]
    listed = client.get("/personal-info").json()
    assert listed["categories"]["contact"] == "联系方式"
    assert listed["items"][0]["aliases"] == ["alternate email"]

    edited = client.put(f"/personal-info/{field_id}", json={"value": "updated@example.com", "status": "confirmed"})
    assert edited.status_code == 200
    assert edited.json()["value"] == "updated@example.com"
    assert client.delete(f"/personal-info/{field_id}").json() == {"ok": True}
    assert client.get("/personal-info").json()["items"] == []


def test_secret_like_values_are_rejected(personal_data_dir) -> None:
    with pytest.raises(ValueError):
        upsert_field(field_key="custom_api_key", value="api_key=sk-abcdefghijklmnop")


def test_form_commands_have_safe_no_model_fallback(personal_data_dir) -> None:
    plan = legacy_rule_fallback("帮我填页面的表单", snapshot_id="snapshot-1", has_browser=True)
    assert plan is not None
    assert plan.action == "delegate"
    assert plan.delegations[0].agent == "web"
    missing = legacy_rule_fallback("记住这个表单中所填的内容", has_browser=False)
    assert missing is not None
    assert missing.action == "clarify"

    record = legacy_rule_fallback("记录表单信息", snapshot_id="snapshot-1", has_browser=True)
    assert record is not None
    assert record.action == "delegate"
    assert record.intent_understanding.operation_classes == ["inspect", "save"]
    assert record.delegations[0].agent == "web"
    assert WebAgent().is_confirmed("browser.remember_current_form", {}, "记录表单信息")


def test_complex_campus_application_preserves_education_as_linked_records(personal_data_dir) -> None:
    scalar_fields = [
        field("dp-field-0", label="姓名", value="程旭升", section_title="个人信息"),
        field("dp-field-1", label="邮箱", value="18419571168@163.com", section_title="个人信息"),
        field("dp-field-2", label="性别", value="男", display_value="男", field_type="custom_radio", section_title="个人信息"),
        field("dp-field-3", label="手机号码", value="18419571168", section_title="个人信息"),
        field("dp-field-4", label="最高学位", value="master", display_value="硕士", field_type="custom_select", section_title="个人信息"),
    ]
    education_1 = [
        field("dp-field-10", label="学校名称", value="河海大学", section_title="教育经历", record_key="education:0", record_index=0),
        field("dp-field-11", label="开始时间", value="2020-09", section_title="教育经历", record_key="education:0", record_index=0),
        field("dp-field-12", label="结束时间", value="2024-06", section_title="教育经历", record_key="education:0", record_index=0),
        field("dp-field-13", label="学院名称", value="地理与遥感学院", section_title="教育经历", record_key="education:0", record_index=0),
        field("dp-field-14", label="专业类别", value="geo", display_value="地理科学类", field_type="custom_select", section_title="教育经历", record_key="education:0", record_index=0),
        field("dp-field-15", label="专业名称", value="地理信息系统", section_title="教育经历", record_key="education:0", record_index=0),
        field("dp-field-16", label="学历", value="bachelor", display_value="本科", field_type="custom_select", section_title="教育经历", record_key="education:0", record_index=0),
    ]
    education_2 = [
        field("dp-field-20", label="学校名称", value="南京大学", section_title="教育经历", record_key="education:1", record_index=1),
        field("dp-field-21", label="开始时间", value="2024-09", section_title="教育经历", record_key="education:1", record_index=1),
        field("dp-field-22", label="学历", value="master", display_value="硕士", field_type="custom_select", section_title="教育经历", record_key="education:1", record_index=1),
    ]
    result = remember_form({"url": "https://campus.example/apply", "title": "校招网申", "fields": [*scalar_fields, *education_1, *education_2]})
    assert result["learned_count"] == 15
    assert len(result["records"]) == 2
    first = result["records"][0]
    assert first["label"] == "河海大学"
    assert {item["field_key"]: item["value"] for item in first["fields"]} == {
        "school": "河海大学", "education_start_date": "2020-09", "education_end_date": "2024-06",
        "college": "地理与遥感学院", "major_category": "地理科学类", "major": "地理信息系统", "degree": "本科",
    }
    assert {item["field_key"] for item in list_fields()} >= {"full_name", "email", "gender", "phone", "degree"}

    target = {"url": "https://jobs.example/form", "fields": [
        field("target-school", label="毕业院校", section_title="教育经历", record_key="education:1", record_index=1),
        field("target-start", label="入学时间", section_title="教育经历", record_key="education:1", record_index=1),
        field("target-degree", label="学历", field_type="custom_select", section_title="教育经历", record_key="education:1", record_index=1),
    ]}
    matches = match_form(target)
    assert {(item["field_id"], item["value"]) for item in matches["assignments"]} == {
        ("target-school", "南京大学"), ("target-start", "2024-09"), ("target-degree", "硕士"),
    }


def test_linked_record_api_supports_field_edit_and_record_delete(personal_data_dir) -> None:
    result = remember_form({"url": "https://campus.example/apply", "fields": [
        field("school", label="学校名称", value="河海大学", section_title="教育经历", record_key="education:0"),
        field("major", label="专业名称", value="地理信息系统", section_title="教育经历", record_key="education:0"),
    ]})
    record_id = result["records"][0]["id"]
    client = TestClient(app)
    overview = client.get("/personal-info").json()
    assert [item["field_key"] for item in overview["records"][0]["fields"]] == ["school", "major"]
    assert overview["records"][0]["fields"][1]["value"] == "地理信息系统"
    edited = client.put(f"/personal-info/records/{record_id}/fields/major", json={"value": "地图学与地理信息系统"})
    assert edited.status_code == 200
    assert {item["field_key"]: item["value"] for item in edited.json()["fields"]}["major"] == "地图学与地理信息系统"
    assert client.delete(f"/personal-info/records/{record_id}").json() == {"ok": True}
    assert client.get("/personal-info").json()["records"] == []


def test_project_skills_and_multi_version_answers_are_first_class_records(personal_data_dir) -> None:
    first = upsert_record(category="qa", fields=[{
        "field_key": "self_evaluation", "label": "自我评价", "value": "偏技术与交付版本",
    }], source_type="user_edit", source_ref=None)
    second = upsert_record(category="qa", fields=[{
        "field_key": "self_evaluation", "label": "自我评价", "value": "偏团队协作版本",
    }], source_type="user_edit", source_ref=None)
    assert first["id"] != second["id"]
    assert [record["label"] for record in list_records(category="qa")] == ["偏技术与交付版本", "偏团队协作版本"]
    assert classify_field(field("project", label="项目描述"))[0] == "project_description"
    assert classify_field(field("certificate", label="证书名称"))[0] == "certificate_name"


def test_form_plan_requires_one_linked_record_choice_and_never_mixes_experiences(personal_data_dir) -> None:
    first = upsert_record(category="work", fields=[
        {"field_key": "company", "label": "公司", "value": "甲公司"},
        {"field_key": "job_title", "label": "岗位", "value": "数据分析师"},
        {"field_key": "work_description", "label": "工作内容", "value": "负责甲项目的数据分析"},
    ], source_type="user_edit", source_ref=None)
    second = upsert_record(category="work", fields=[
        {"field_key": "company", "label": "公司", "value": "乙公司"},
        {"field_key": "job_title", "label": "岗位", "value": "产品经理"},
        {"field_key": "work_description", "label": "工作内容", "value": "负责乙产品的规划与交付"},
    ], source_type="user_edit", source_ref=None)
    page = {"url": "https://jobs.example/apply", "fields": [
        field("company", label="实习单位", section_title="实习经历", record_key="work:0"),
        field("title", label="实习岗位", section_title="实习经历", record_key="work:0"),
        field("description", label="工作内容", field_type="textarea", section_title="实习经历", record_key="work:0"),
    ]}
    plan = create_form_session(page)
    assert plan["groups"][0]["status"] == "choose"
    assert {candidate["record_id"] for candidate in plan["groups"][0]["candidates"]} == {first["id"], second["id"]}
    assert plan["auto_assignments"] == []
    resolved = resolve_form_session(plan["session_id"], {
        "groups": {"work:0": second["id"]}, "fields": {}, "remember": True,
    })
    assert {assignment["record_id"] for assignment in resolved["assignments"]} == {second["id"]}
    assert {assignment["value"] for assignment in resolved["assignments"]} == {"乙公司", "产品经理", "负责乙产品的规划与交付"}


def test_form_plan_protects_existing_sensitive_choice_and_long_text_fields(personal_data_dir) -> None:
    upsert_field(field_key="full_name", value="程旭升")
    upsert_field(field_key="phone", value="13800138000")
    upsert_field(field_key="gender", value="男")
    page = {"url": "https://jobs.example/apply", "fields": [
        field("name", label="申请人姓名"),
        field("phone", label="联系电话", value="页面已有号码"),
        field("gender", label="性别", field_type="custom_select"),
    ]}
    plan = create_form_session(page)
    by_id = {item["field_id"]: item for item in plan["fields"]}
    assert by_id["name"]["status"] == "ready"
    assert by_id["phone"]["status"] == "existing"
    assert by_id["gender"]["status"] == "confirm"
    blocked = resolve_form_session(plan["session_id"], {
        "fields": {"phone": {"action": "fill"}}, "groups": {}, "apply_ready": False,
    })
    assert blocked["assignments"] == []
    allowed = resolve_form_session(plan["session_id"], {
        "fields": {"phone": {"action": "fill", "replace_existing": True}},
        "groups": {}, "apply_ready": False,
    })
    assert allowed["assignments"][0]["field_id"] == "phone"
    assert allowed["assignments"][0]["value"] == "13800138000"
    assert allowed["assignments"][0]["allow_overwrite"] is True
    assert allowed["assignments"][0]["expected_current_value"] == "页面已有号码"


def test_confirmed_record_choice_is_saved_as_editable_site_memory(personal_data_dir) -> None:
    project = upsert_record(category="project", fields=[
        {"field_key": "project_name", "label": "项目名称", "value": "DeskPilot"},
        {"field_key": "project_role", "label": "项目角色", "value": "核心开发"},
    ], source_type="user_edit", source_ref=None)
    other = upsert_record(category="project", fields=[
        {"field_key": "project_name", "label": "项目名称", "value": "知识库"},
        {"field_key": "project_role", "label": "项目角色", "value": "维护者"},
    ], source_type="user_edit", source_ref=None)
    page = {"url": "https://campus.example/application", "fields": [
        field("project-name", label="项目名称", section_title="项目经历", record_key="project:0"),
        field("project-role", label="项目角色", section_title="项目经历", record_key="project:0"),
    ]}
    plan = create_form_session(page)
    resolved = resolve_form_session(plan["session_id"], {
        "groups": {"project:0": project["id"]}, "fields": {}, "remember": True,
    })
    assert other["id"] != project["id"]
    finalized = finalize_form_session(plan["session_id"], resolved["resolutions"],
                                      [item["field_id"] for item in resolved["assignments"]])
    assert all(item["status"] == "filled" for item in finalized["fields"])
    memories = list_form_memories()
    assert len(memories) == 2
    assert {memory["source_record_id"] for memory in memories} == {project["id"]}


def test_dynamic_form_paths_reuse_confirmed_record_preference(personal_data_dir) -> None:
    captured = {"url": "https://jobs.example/apply/42", "fields": [
        field("project-name", label="项目名称", value="DeskPilot", section_title="项目经历", record_key="project:0"),
        field("project-role", label="项目角色", value="核心开发", section_title="项目经历", record_key="project:0"),
    ]}
    remembered = remember_form(captured)
    preferred = remembered["records"][0]
    upsert_record(category="project", fields=[
        {"field_key": "project_name", "label": "项目名称", "value": "另一个项目"},
        {"field_key": "project_role", "label": "项目角色", "value": "参与者"},
    ], source_type="user_edit", source_ref=None)
    plan = build_form_plan({"url": "https://jobs.example/apply/43", "fields": [
        field("target-name", label="项目名称", section_title="项目经历", record_key="project:0"),
        field("target-role", label="项目角色", section_title="项目经历", record_key="project:0"),
    ]})
    assert plan["groups"][0]["remembered"] is True
    assert plan["groups"][0]["selected_record_id"] == preferred["id"]
    assert {assignment["record_id"] for assignment in plan["auto_assignments"]} == {preferred["id"]}
    assert {memory["path_pattern"] for memory in list_form_memories()} == {"/apply/:id"}


def test_form_memory_api_supports_view_update_and_delete(personal_data_dir) -> None:
    remember_form({"url": "https://jobs.example/apply", "fields": [
        field("email", label="邮箱", value="alice@example.com"),
    ]})
    client = TestClient(app)
    overview = client.get("/personal-info").json()
    memory_id = overview["form_memories"][0]["id"]
    edited = client.put(f"/personal-info/form-memories/{memory_id}", json={
        "action": "literal", "override_value": "site@example.com", "priority": 200,
    })
    assert edited.status_code == 200
    assert edited.json()["override_value"] == "site@example.com"
    assert edited.json()["priority"] == 200
    assert client.delete(f"/personal-info/form-memories/{memory_id}").json() == {"ok": True}
    assert client.get("/personal-info").json()["form_memories"] == []


def test_agent_observation_only_exposes_form_session_reference(personal_data_dir) -> None:
    upsert_field(field_key="full_name", value="不应进入模型观察的姓名")
    plan = create_form_session({"url": "https://jobs.example/apply", "fields": [
        field("name", label="姓名"),
    ]})
    reference = _session_reference(plan)
    assert reference["session_id"] == plan["session_id"]
    assert "fields" not in reference
    assert "groups" not in reference
    assert "不应进入模型观察的姓名" not in str(reference)
    fetched = TestClient(app).get(f"/personal-info/form-sessions/{plan['session_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["fields"][0]["selected"]["value"] == "不应进入模型观察的姓名"
