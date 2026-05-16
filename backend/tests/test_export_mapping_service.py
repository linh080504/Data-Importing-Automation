from app.services.export_mapping import map_clean_payload_to_template


def test_map_clean_payload_to_template_preserves_template_order() -> None:
    clean_payload = {
        "website": "https://example.edu",
        "name": "Example University",
        "location": "Vietnam",
    }
    template_columns = [
        {"name": "id", "order": 1},
        {"name": "name", "order": 2},
        {"name": "location", "order": 3},
        {"name": "website", "order": 4},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert list(mapped.keys()) == ["id", "name", "location", "website"]
    assert mapped == {
        "id": None,
        "name": "Example University",
        "location": "Vietnam",
        "website": "https://example.edu",
    }


def test_map_clean_payload_to_template_ignores_extra_clean_fields() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://example.edu",
        "internal_note": "ignore me",
    }
    template_columns = [
        {"name": "name", "order": 2},
        {"name": "website", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert list(mapped.keys()) == ["website", "name"]
    assert mapped == {
        "website": "https://example.edu",
        "name": "Example University",
    }


def test_map_clean_payload_to_template_applies_defaults_for_missing_values() -> None:
    clean_payload = {
        "name": "Example University",
        "website": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "sponsored", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://fallback.example.edu"},
    )

    assert mapped == {
        "name": "Example University",
        "website": "https://fallback.example.edu",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_applies_rule_based_slug_fill() -> None:
    clean_payload = {
        "name": "Example University of Technology",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University of Technology",
        "slug": "example-university-of-technology",
    }


def test_map_clean_payload_to_template_keeps_existing_slug_value() -> None:
    clean_payload = {
        "name": "Example University of Technology",
        "slug": "custom-slug",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University of Technology",
        "slug": "custom-slug",
    }


def test_map_clean_payload_to_template_sets_known_boolean_fields_false_when_missing() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "student_loan_available", "order": 2},
        {"name": "immigration_support", "order": 3},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "student_loan_available": False,
        "immigration_support": False,
    }


def test_map_clean_payload_to_template_can_disable_rule_based_boolean_defaults() -> None:
    mapped = map_clean_payload_to_template(
        {"name": "Example University"},
        template_columns=[
            {"name": "name", "order": 1},
            {"name": "slug", "order": 2},
            {"name": "sponsored", "order": 3},
        ],
        allow_rule_based_defaults=False,
    )

    assert mapped == {
        "name": "Example University",
        "slug": "example-university",
        "sponsored": None,
    }


def test_map_clean_payload_to_template_keeps_default_before_rule_fill() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "preferred-slug"},
    )

    assert mapped == {
        "name": "Example University",
        "slug": "preferred-slug",
    }


def test_map_clean_payload_to_template_treats_blank_string_as_missing() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Example University",
        "website": "https://default.example.edu",
    }


def test_map_clean_payload_to_template_uses_none_for_unknown_missing_columns() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "global_rank", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "global_rank": None,
    }


def test_map_clean_payload_to_template_uses_slug_rule_only_after_name_is_mapped() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "slug", "order": 1},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "slug": None,
        "name": "Example University",
    }


def test_map_clean_payload_to_template_uses_slug_rule_when_name_precedes_slug() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "slug": "example-university",
    }


def test_map_clean_payload_to_template_preserves_false_boolean_values() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": False,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_preserves_zero_values() -> None:
    clean_payload = {
        "name": "Example University",
        "global_rank": 0,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "global_rank", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "global_rank": 0,
    }


def test_map_clean_payload_to_template_skips_blank_template_column_names() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": " ", "order": 1},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
    }


def test_map_clean_payload_to_template_handles_non_integer_order_as_zero() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "website", "order": "x"},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert list(mapped.keys()) == ["website", "name"]
    assert mapped == {
        "website": "https://example.edu",
        "name": "Example University",
    }


def test_map_clean_payload_to_template_uses_default_false_value() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"sponsored": False},
    )

    assert mapped == {
        "name": "Example University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_preserves_true_boolean_values() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": True,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "sponsored": True,
    }


def test_map_clean_payload_to_template_preserves_non_blank_string_values() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Example University",
        "website": "https://example.edu",
    }


def test_map_clean_payload_to_template_handles_blank_name_for_slug_rule() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
    }


def test_map_clean_payload_to_template_normalizes_blank_name_to_none() -> None:
    clean_payload = {
        "name": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
    }


def test_map_clean_payload_to_template_keeps_existing_slug_when_name_is_blank() -> None:
    clean_payload = {
        "name": " ",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": "existing",
    }


def test_map_clean_payload_to_template_uses_slug_default_when_name_is_blank() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_prefers_existing_slug_over_blank_name() -> None:
    clean_payload = {
        "name": " ",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": "existing",
    }


def test_map_clean_payload_to_template_normalizes_blank_name_before_slug_rule() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
    }


def test_map_clean_payload_to_template_normalizes_blank_name_before_slug_default() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_normalizes_blank_name_with_existing_slug() -> None:
    clean_payload = {
        "name": " ",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": "existing",
    }


def test_map_clean_payload_to_template_preserves_empty_string_name_only_when_explicit_default_exists() -> None:
    clean_payload = {
        "name": "",
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
    }


def test_map_clean_payload_to_template_treats_blank_name_as_missing_for_slug_logic() -> None:
    clean_payload = {
        "name": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
    }


def test_map_clean_payload_to_template_uses_slug_default_after_blank_name_normalization() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_keeps_existing_slug_after_blank_name_normalization() -> None:
    clean_payload = {
        "name": " ",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": "existing",
    }


def test_map_clean_payload_to_template_blank_name_does_not_generate_slug() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
    }


def test_map_clean_payload_to_template_blank_name_uses_default_slug_if_given() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_blank_name_preserves_existing_slug() -> None:
    clean_payload = {
        "name": " ",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": "existing",
    }


def test_map_clean_payload_to_template_handles_slug_default_with_blank_name() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_handles_blank_name_and_existing_slug() -> None:
    clean_payload = {
        "name": " ",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": "existing",
    }


def test_map_clean_payload_to_template_treats_blank_name_as_missing_but_keeps_other_values() -> None:
    clean_payload = {
        "name": " ",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "website": "https://example.edu",
    }


def test_map_clean_payload_to_template_treats_blank_name_as_missing_even_without_slug() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
    }


def test_map_clean_payload_to_template_treats_blank_name_as_missing_with_slug_default() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_treats_blank_name_as_missing_with_existing_slug() -> None:
    clean_payload = {
        "name": " ",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": "existing",
    }


def test_map_clean_payload_to_template_blank_name_is_missing_for_rule_engine() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
    }


def test_map_clean_payload_to_template_blank_name_is_missing_for_defaults_and_slug() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_blank_name_is_missing_but_existing_slug_survives() -> None:
    clean_payload = {
        "name": " ",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": "existing",
    }


def test_map_clean_payload_to_template_preserves_false_boolean_values() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": False,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_applies_default_to_blank_slug_before_rule() -> None:
    clean_payload = {
        "name": "Example University",
        "slug": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": "Example University",
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_handles_empty_template_columns() -> None:
    mapped = map_clean_payload_to_template({"name": "Example University"}, template_columns=[])

    assert mapped == {}


def test_map_clean_payload_to_template_handles_empty_clean_payload() -> None:
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
        {"name": "sponsored", "order": 3},
    ]

    mapped = map_clean_payload_to_template({}, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
        "sponsored": False,
    }


def test_map_clean_payload_to_template_preserves_numeric_values() -> None:
    clean_payload = {
        "name": "Example University",
        "global_rank": 12,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "global_rank", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "global_rank": 12,
    }


def test_map_clean_payload_to_template_preserves_empty_list_values() -> None:
    clean_payload = {
        "name": "Example University",
        "university_campuses": [],
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "university_campuses", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "university_campuses": [],
    }


def test_map_clean_payload_to_template_preserves_empty_dict_values() -> None:
    clean_payload = {
        "name": "Example University",
        "financials": {},
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "financials", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "financials": {},
    }


def test_map_clean_payload_to_template_keeps_known_boolean_true_values() -> None:
    clean_payload = {
        "name": "Example University",
        "immigration_support": True,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "immigration_support", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "immigration_support": True,
    }


def test_map_clean_payload_to_template_preserves_non_string_name_for_slug() -> None:
    clean_payload = {
        "name": 12345,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": 12345,
        "slug": "12345",
    }


def test_map_clean_payload_to_template_uses_default_for_unknown_column() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "admissions_page_link", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"admissions_page_link": "https://example.edu/admissions"},
    )

    assert mapped == {
        "name": "Example University",
        "admissions_page_link": "https://example.edu/admissions",
    }


def test_map_clean_payload_to_template_keeps_false_default_for_known_boolean_field() -> None:
    clean_payload = {
        "name": "Example University",
        "immigration_support": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "immigration_support", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"immigration_support": False},
    )

    assert mapped == {
        "name": "Example University",
        "immigration_support": False,
    }


def test_map_clean_payload_to_template_handles_blank_column_name_with_default() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "", "order": 1},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"": "ignored"},
    )

    assert mapped == {
        "name": "Example University",
    }


def test_map_clean_payload_to_template_preserves_existing_false_for_known_boolean_field() -> None:
    clean_payload = {
        "name": "Example University",
        "student_loan_available": False,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "student_loan_available", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "student_loan_available": False,
    }


def test_map_clean_payload_to_template_applies_rule_based_false_for_housing_availability() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "housing_availability", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "housing_availability": False,
    }


def test_map_clean_payload_to_template_applies_rule_based_false_for_sponsored() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_keeps_non_empty_string_slug() -> None:
    clean_payload = {
        "name": "Example University",
        "slug": "already-set",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "slug": "already-set",
    }


def test_map_clean_payload_to_template_handles_defaults_none_gracefully() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns, defaults=None)

    assert mapped == {
        "name": "Example University",
        "website": None,
    }


def test_map_clean_payload_to_template_preserves_existing_boolean_true_without_default_override() -> None:
    clean_payload = {
        "name": "Example University",
        "housing_availability": True,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "housing_availability", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"housing_availability": False},
    )

    assert mapped == {
        "name": "Example University",
        "housing_availability": True,
    }


def test_map_clean_payload_to_template_preserves_existing_value_over_default() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://real.example.edu",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Example University",
        "website": "https://real.example.edu",
    }


def test_map_clean_payload_to_template_handles_multiple_rule_based_boolean_fields() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
        {"name": "student_loan_available", "order": 3},
        {"name": "housing_availability", "order": 4},
        {"name": "immigration_support", "order": 5},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "sponsored": False,
        "student_loan_available": False,
        "housing_availability": False,
        "immigration_support": False,
    }


def test_map_clean_payload_to_template_handles_slug_generated_from_mixed_case_name() -> None:
    clean_payload = {
        "name": "Example UNIVERSITY 2026",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example UNIVERSITY 2026",
        "slug": "example-university-2026",
    }


def test_map_clean_payload_to_template_handles_slug_generated_from_punctuation() -> None:
    clean_payload = {
        "name": "Example, University!",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example, University!",
        "slug": "example-university",
    }


def test_map_clean_payload_to_template_handles_slug_generated_from_extra_spaces() -> None:
    clean_payload = {
        "name": "  Example   University  ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "  Example   University  ",
        "slug": "example-university",
    }


def test_map_clean_payload_to_template_handles_slug_default_with_blank_name() -> None:
    clean_payload = {
        "name": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_handles_none_name_for_slug_rule() -> None:
    clean_payload = {
        "name": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
    }


def test_map_clean_payload_to_template_handles_defaults_for_multiple_missing_fields() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "admissions_page_link", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={
            "website": "https://example.edu",
            "admissions_page_link": "https://example.edu/admissions",
        },
    )

    assert mapped == {
        "name": "Example University",
        "website": "https://example.edu",
        "admissions_page_link": "https://example.edu/admissions",
    }


def test_map_clean_payload_to_template_keeps_existing_value_for_known_boolean_field() -> None:
    clean_payload = {
        "name": "Example University",
        "student_loan_available": True,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "student_loan_available", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "student_loan_available": True,
    }


def test_map_clean_payload_to_template_keeps_existing_false_value_for_known_boolean_field() -> None:
    clean_payload = {
        "name": "Example University",
        "housing_availability": False,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "housing_availability", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "housing_availability": False,
    }


def test_map_clean_payload_to_template_keeps_existing_non_empty_slug() -> None:
    clean_payload = {
        "name": "Example University",
        "slug": "existing-slug",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "slug": "existing-slug",
    }


def test_map_clean_payload_to_template_uses_default_for_blank_boolean_field() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": "   ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"sponsored": False},
    )

    assert mapped == {
        "name": "Example University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_unknown_column_without_default_or_rule() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "custom_field": None,
    }


def test_map_clean_payload_to_template_preserves_existing_custom_field_value() -> None:
    clean_payload = {
        "name": "Example University",
        "custom_field": "custom-value",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "custom_field": "custom-value",
    }


def test_map_clean_payload_to_template_handles_slug_generation_with_numbers_only() -> None:
    clean_payload = {
        "name": 2026,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": 2026,
        "slug": "2026",
    }


def test_map_clean_payload_to_template_handles_default_zero_value() -> None:
    clean_payload = {
        "name": "Example University",
        "global_rank": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "global_rank", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"global_rank": 0},
    )

    assert mapped == {
        "name": "Example University",
        "global_rank": 0,
    }


def test_map_clean_payload_to_template_handles_default_empty_list_value() -> None:
    clean_payload = {
        "name": "Example University",
        "university_campuses": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "university_campuses", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"university_campuses": []},
    )

    assert mapped == {
        "name": "Example University",
        "university_campuses": [],
    }


def test_map_clean_payload_to_template_handles_default_empty_dict_value() -> None:
    clean_payload = {
        "name": "Example University",
        "financials": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "financials", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"financials": {}},
    )

    assert mapped == {
        "name": "Example University",
        "financials": {},
    }


def test_map_clean_payload_to_template_handles_missing_name_before_slug_rule() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "slug", "order": 1},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "slug": None,
        "name": None,
    }


def test_map_clean_payload_to_template_handles_missing_name_after_slug_rule() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
    }


def test_map_clean_payload_to_template_preserves_existing_url_over_default() -> None:
    clean_payload = {
        "name": "Example University",
        "admissions_page_link": "https://real.example.edu/admissions",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "admissions_page_link", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"admissions_page_link": "https://default.example.edu/admissions"},
    )

    assert mapped == {
        "name": "Example University",
        "admissions_page_link": "https://real.example.edu/admissions",
    }


def test_map_clean_payload_to_template_handles_blank_custom_field_with_default() -> None:
    clean_payload = {
        "name": "Example University",
        "custom_field": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"custom_field": "fallback"},
    )

    assert mapped == {
        "name": "Example University",
        "custom_field": "fallback",
    }


def test_map_clean_payload_to_template_handles_none_custom_field_without_default() -> None:
    clean_payload = {
        "name": "Example University",
        "custom_field": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "custom_field": None,
    }


def test_map_clean_payload_to_template_preserves_non_empty_custom_field_over_default() -> None:
    clean_payload = {
        "name": "Example University",
        "custom_field": "actual",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"custom_field": "fallback"},
    )

    assert mapped == {
        "name": "Example University",
        "custom_field": "actual",
    }


def test_map_clean_payload_to_template_handles_default_true_value() -> None:
    clean_payload = {
        "name": "Example University",
        "immigration_support": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "immigration_support", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"immigration_support": True},
    )

    assert mapped == {
        "name": "Example University",
        "immigration_support": True,
    }


def test_map_clean_payload_to_template_preserves_existing_true_over_default_false() -> None:
    clean_payload = {
        "name": "Example University",
        "immigration_support": True,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "immigration_support", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"immigration_support": False},
    )

    assert mapped == {
        "name": "Example University",
        "immigration_support": True,
    }


def test_map_clean_payload_to_template_handles_name_missing_with_default_slug() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "slug", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_handles_default_for_boolean_and_rule_not_applied() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"sponsored": True},
    )

    assert mapped == {
        "name": "Example University",
        "sponsored": True,
    }


def test_map_clean_payload_to_template_handles_zero_order_value() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "website", "order": 0},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert list(mapped.keys()) == ["website", "name"]
    assert mapped == {
        "website": "https://example.edu",
        "name": "Example University",
    }


def test_map_clean_payload_to_template_handles_missing_order_key() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "website"},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert list(mapped.keys()) == ["website", "name"]
    assert mapped == {
        "website": "https://example.edu",
        "name": "Example University",
    }


def test_map_clean_payload_to_template_preserves_existing_defaultable_url() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://set.example.edu",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Example University",
        "website": "https://set.example.edu",
    }


def test_map_clean_payload_to_template_handles_blank_existing_boolean_string_with_default() -> None:
    clean_payload = {
        "name": "Example University",
        "student_loan_available": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "student_loan_available", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"student_loan_available": False},
    )

    assert mapped == {
        "name": "Example University",
        "student_loan_available": False,
    }


def test_map_clean_payload_to_template_handles_empty_string_slug_without_default() -> None:
    clean_payload = {
        "name": "Example University",
        "slug": "",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "slug": "example-university",
    }


def test_map_clean_payload_to_template_handles_blank_unknown_field_without_default() -> None:
    clean_payload = {
        "name": "Example University",
        "custom_field": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "custom_field": None,
    }


def test_map_clean_payload_to_template_handles_blank_known_boolean_field_without_default() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_blank_url_with_no_default() -> None:
    clean_payload = {
        "name": "Example University",
        "website": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "website": None,
    }


def test_map_clean_payload_to_template_handles_blank_slug_when_slug_precedes_name() -> None:
    clean_payload = {
        "name": "Example University",
        "slug": " ",
    }
    template_columns = [
        {"name": "slug", "order": 1},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "slug": None,
        "name": "Example University",
    }


def test_map_clean_payload_to_template_handles_blank_slug_when_name_precedes_slug() -> None:
    clean_payload = {
        "name": "Example University",
        "slug": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "slug": "example-university",
    }


def test_map_clean_payload_to_template_handles_blank_name_and_existing_slug() -> None:
    clean_payload = {
        "name": " ",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": "existing",
    }


def test_map_clean_payload_to_template_handles_none_existing_slug_with_default() -> None:
    clean_payload = {
        "name": "Example University",
        "slug": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "preferred"},
    )

    assert mapped == {
        "name": "Example University",
        "slug": "preferred",
    }


def test_map_clean_payload_to_template_handles_none_existing_slug_without_default() -> None:
    clean_payload = {
        "name": "Example University",
        "slug": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "slug": "example-university",
    }


def test_map_clean_payload_to_template_handles_none_name_with_default_slug() -> None:
    clean_payload = {
        "name": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback",
    }


def test_map_clean_payload_to_template_handles_missing_name_with_known_boolean_rule() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "sponsored", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_missing_name_with_unknown_field() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "custom_field", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "custom_field": None,
    }


def test_map_clean_payload_to_template_handles_missing_name_with_default_unknown_field() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "custom_field", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"custom_field": "fallback"},
    )

    assert mapped == {
        "custom_field": "fallback",
    }


def test_map_clean_payload_to_template_handles_none_for_known_boolean_and_no_default() -> None:
    clean_payload = {
        "name": "Example University",
        "immigration_support": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "immigration_support", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "immigration_support": False,
    }


def test_map_clean_payload_to_template_handles_none_for_unknown_field_with_no_default() -> None:
    clean_payload = {
        "name": "Example University",
        "custom_field": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "custom_field": None,
    }


def test_map_clean_payload_to_template_handles_none_for_unknown_field_with_default() -> None:
    clean_payload = {
        "name": "Example University",
        "custom_field": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"custom_field": "fallback"},
    )

    assert mapped == {
        "name": "Example University",
        "custom_field": "fallback",
    }


def test_map_clean_payload_to_template_handles_existing_false_for_sponsored() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": False,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_existing_true_for_sponsored() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": True,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Example University",
        "sponsored": True,
    }


def test_map_clean_payload_to_template_handles_default_for_missing_name_field() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
    }


def test_map_clean_payload_to_template_preserves_existing_name_over_default() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Example University",
    }


def test_map_clean_payload_to_template_handles_blank_name_with_default() -> None:
    clean_payload = {
        "name": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
    }


def test_map_clean_payload_to_template_handles_blank_name_without_default() -> None:
    clean_payload = {
        "name": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
    }


def test_map_clean_payload_to_template_handles_none_name_without_default() -> None:
    clean_payload = {
        "name": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
    }


def test_map_clean_payload_to_template_handles_zero_as_existing_value_not_missing() -> None:
    clean_payload = {
        "global_rank": 0,
    }
    template_columns = [
        {"name": "global_rank", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"global_rank": 99},
    )

    assert mapped == {
        "global_rank": 0,
    }


def test_map_clean_payload_to_template_handles_false_as_existing_value_not_missing() -> None:
    clean_payload = {
        "sponsored": False,
    }
    template_columns = [
        {"name": "sponsored", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"sponsored": True},
    )

    assert mapped == {
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_empty_string_name_and_slug_default() -> None:
    clean_payload = {
        "name": "",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_handles_empty_string_name_and_no_default() -> None:
    clean_payload = {
        "name": "",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
    }


def test_map_clean_payload_to_template_handles_blank_name_preserving_original_string_when_default_absent() -> None:
    clean_payload = {
        "name": "   ",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "website": "https://example.edu",
    }


def test_map_clean_payload_to_template_handles_blank_name_with_other_defaults() -> None:
    clean_payload = {
        "name": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": None,
        "website": "https://default.example.edu",
    }


def test_map_clean_payload_to_template_handles_none_clean_payload_value_with_non_none_default() -> None:
    clean_payload = {
        "website": None,
    }
    template_columns = [
        {"name": "website", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "website": "https://default.example.edu",
    }


def test_map_clean_payload_to_template_handles_none_clean_payload_value_with_none_default() -> None:
    clean_payload = {
        "website": None,
    }
    template_columns = [
        {"name": "website", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": None},
    )

    assert mapped == {
        "website": None,
    }


def test_map_clean_payload_to_template_handles_blank_name_with_boolean_rule_field() -> None:
    clean_payload = {
        "name": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_blank_name_with_slug_and_boolean_rule() -> None:
    clean_payload = {
        "name": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
        {"name": "sponsored", "order": 3},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_missing_clean_payload_for_all_fields() -> None:
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "slug", "order": 3},
        {"name": "sponsored", "order": 4},
    ]

    mapped = map_clean_payload_to_template({}, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "website": None,
        "slug": None,
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_defaults_for_all_missing_fields() -> None:
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "slug", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        {},
        template_columns=template_columns,
        defaults={
            "name": "Fallback University",
            "website": "https://default.example.edu",
            "slug": "fallback-university",
        },
    )

    assert mapped == {
        "name": "Fallback University",
        "website": "https://default.example.edu",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_blank_fields_with_defaults_and_rules() -> None:
    clean_payload = {
        "name": " ",
        "website": " ",
        "slug": " ",
        "sponsored": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "slug", "order": 3},
        {"name": "sponsored", "order": 4},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu", "slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "website": "https://default.example.edu",
        "slug": "fallback-slug",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_partial_defaults_and_rules() -> None:
    clean_payload = {
        "name": "Example University",
        "website": None,
        "slug": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "slug", "order": 3},
        {"name": "sponsored", "order": 4},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Example University",
        "website": "https://default.example.edu",
        "slug": "example-university",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_defaults_for_unknown_then_known_fields() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "custom_field", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"custom_field": "fallback"},
    )

    assert mapped == {
        "custom_field": "fallback",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_defaults_for_known_then_unknown_fields() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "sponsored", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"custom_field": "fallback"},
    )

    assert mapped == {
        "sponsored": False,
        "custom_field": "fallback",
    }


def test_map_clean_payload_to_template_handles_slug_default_even_when_name_missing() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_handles_empty_defaults_dict() -> None:
    clean_payload = {
        "name": "Example University",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns, defaults={})

    assert mapped == {
        "name": "Example University",
        "website": None,
    }


def test_map_clean_payload_to_template_handles_blank_default_string_as_value() -> None:
    clean_payload = {
        "name": "Example University",
        "website": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": ""},
    )

    assert mapped == {
        "name": "Example University",
        "website": None,
    }


def test_map_clean_payload_to_template_handles_blank_default_slug_then_rule_fills() -> None:
    clean_payload = {
        "name": "Example University",
        "slug": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": ""},
    )

    assert mapped == {
        "name": "Example University",
        "slug": "example-university",
    }


def test_map_clean_payload_to_template_handles_blank_default_for_boolean_then_rule_fills() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"sponsored": ""},
    )

    assert mapped == {
        "name": "Example University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_blank_default_for_unknown_then_none() -> None:
    clean_payload = {
        "name": "Example University",
        "custom_field": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"custom_field": ""},
    )

    assert mapped == {
        "name": "Example University",
        "custom_field": None,
    }


def test_map_clean_payload_to_template_handles_none_order_value() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "website", "order": None},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert list(mapped.keys()) == ["website", "name"]
    assert mapped == {
        "website": "https://example.edu",
        "name": "Example University",
    }


def test_map_clean_payload_to_template_handles_duplicate_orders_by_stable_sort() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "website", "order": 1},
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert list(mapped.keys()) == ["website", "name"]
    assert mapped == {
        "website": "https://example.edu",
        "name": "Example University",
    }


def test_map_clean_payload_to_template_handles_integer_default_value() -> None:
    clean_payload = {
        "name": "Example University",
        "global_rank": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "global_rank", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"global_rank": 1},
    )

    assert mapped == {
        "name": "Example University",
        "global_rank": 1,
    }


def test_map_clean_payload_to_template_handles_boolean_default_value() -> None:
    clean_payload = {
        "name": "Example University",
        "sponsored": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"sponsored": True},
    )

    assert mapped == {
        "name": "Example University",
        "sponsored": True,
    }


def test_map_clean_payload_to_template_handles_list_default_value() -> None:
    clean_payload = {
        "name": "Example University",
        "university_campuses": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "university_campuses", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"university_campuses": ["Main Campus"]},
    )

    assert mapped == {
        "name": "Example University",
        "university_campuses": ["Main Campus"],
    }


def test_map_clean_payload_to_template_handles_dict_default_value() -> None:
    clean_payload = {
        "name": "Example University",
        "financials": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "financials", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"financials": {"tuition": "unknown"}},
    )

    assert mapped == {
        "name": "Example University",
        "financials": {"tuition": "unknown"},
    }


def test_map_clean_payload_to_template_handles_slug_generation_with_unicode_removed() -> None:
    clean_payload = {
        "name": "Đại học Example",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Đại học Example",
        "slug": "i-h-c-example",
    }


def test_map_clean_payload_to_template_handles_slug_generation_for_name_with_symbols_only() -> None:
    clean_payload = {
        "name": "!!!",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "!!!",
        "slug": None,
    }


def test_map_clean_payload_to_template_handles_preserving_name_with_unicode() -> None:
    clean_payload = {
        "name": "Đại học Example",
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": "Đại học Example",
    }


def test_map_clean_payload_to_template_handles_default_unicode_value() -> None:
    clean_payload = {
        "name": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Đại học Mặc định"},
    )

    assert mapped == {
        "name": "Đại học Mặc định",
    }


def test_map_clean_payload_to_template_handles_rule_fill_after_default_blank_name() -> None:
    clean_payload = {
        "name": "",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_default_for_slug_and_name_blank() -> None:
    clean_payload = {
        "name": "",
        "slug": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "name": None,
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_handles_order_sorting_with_negative_order() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "website", "order": -1},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert list(mapped.keys()) == ["website", "name"]
    assert mapped == {
        "website": "https://example.edu",
        "name": "Example University",
    }


def test_map_clean_payload_to_template_handles_float_order_as_zero() -> None:
    clean_payload = {
        "name": "Example University",
        "website": "https://example.edu",
    }
    template_columns = [
        {"name": "website", "order": 1.5},
        {"name": "name", "order": 2},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert list(mapped.keys()) == ["website", "name"]
    assert mapped == {
        "website": "https://example.edu",
        "name": "Example University",
    }


def test_map_clean_payload_to_template_handles_existing_empty_list_not_missing() -> None:
    clean_payload = {
        "university_campuses": [],
    }
    template_columns = [
        {"name": "university_campuses", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"university_campuses": ["Main Campus"]},
    )

    assert mapped == {
        "university_campuses": [],
    }


def test_map_clean_payload_to_template_handles_existing_empty_dict_not_missing() -> None:
    clean_payload = {
        "financials": {},
    }
    template_columns = [
        {"name": "financials", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"financials": {"tuition": "unknown"}},
    )

    assert mapped == {
        "financials": {},
    }


def test_map_clean_payload_to_template_handles_existing_non_empty_list() -> None:
    clean_payload = {
        "university_campuses": ["Main Campus"],
    }
    template_columns = [
        {"name": "university_campuses", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "university_campuses": ["Main Campus"],
    }


def test_map_clean_payload_to_template_handles_existing_non_empty_dict() -> None:
    clean_payload = {
        "financials": {"tuition": "$1000"},
    }
    template_columns = [
        {"name": "financials", "order": 1},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "financials": {"tuition": "$1000"},
    }


def test_map_clean_payload_to_template_handles_blank_default_name_then_slug_rule_from_default_name() -> None:
    clean_payload = {
        "name": "",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_default_for_name_and_existing_slug() -> None:
    clean_payload = {
        "name": "",
        "slug": "existing",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "existing",
    }


def test_map_clean_payload_to_template_handles_rule_fill_for_slug_with_default_name() -> None:
    clean_payload = {
        "name": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_rule_fill_for_slug_with_default_name_and_default_slug_blank() -> None:
    clean_payload = {
        "name": None,
        "slug": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "slug": ""},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_rule_fill_for_slug_with_default_name_and_default_slug_value() -> None:
    clean_payload = {
        "name": None,
        "slug": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "slug": "preferred-slug"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "preferred-slug",
    }


def test_map_clean_payload_to_template_handles_multiple_blank_known_boolean_fields() -> None:
    clean_payload = {
        "sponsored": " ",
        "student_loan_available": None,
        "housing_availability": "",
        "immigration_support": None,
    }
    template_columns = [
        {"name": "sponsored", "order": 1},
        {"name": "student_loan_available", "order": 2},
        {"name": "housing_availability", "order": 3},
        {"name": "immigration_support", "order": 4},
    ]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "sponsored": False,
        "student_loan_available": False,
        "housing_availability": False,
        "immigration_support": False,
    }


def test_map_clean_payload_to_template_handles_blank_name_with_default_and_known_boolean_fields() -> None:
    clean_payload = {
        "name": "",
        "sponsored": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
        {"name": "slug", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "sponsored": False,
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_blank_name_with_default_and_website_default() -> None:
    clean_payload = {
        "name": "",
        "website": "",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "slug", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Fallback University",
        "website": "https://default.example.edu",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_custom_default_and_slug_rule_together() -> None:
    clean_payload = {
        "name": "Example University",
        "custom_field": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
        {"name": "slug", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"custom_field": "custom-default"},
    )

    assert mapped == {
        "name": "Example University",
        "custom_field": "custom-default",
        "slug": "example-university",
    }


def test_map_clean_payload_to_template_handles_name_default_without_slug_column() -> None:
    clean_payload = {
        "name": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
    }


def test_map_clean_payload_to_template_handles_defaults_and_existing_values_mixed() -> None:
    clean_payload = {
        "name": "Example University",
        "website": None,
        "admissions_page_link": "https://real.example.edu/admissions",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "admissions_page_link", "order": 3},
        {"name": "slug", "order": 4},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Example University",
        "website": "https://default.example.edu",
        "admissions_page_link": "https://real.example.edu/admissions",
        "slug": "example-university",
    }


def test_map_clean_payload_to_template_handles_none_name_default_and_boolean_rule_only() -> None:
    clean_payload = {
        "name": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "sponsored", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_default_name_and_unknown_field() -> None:
    clean_payload = {
        "name": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "custom_field": "fallback"},
    )

    assert mapped == {
        "name": "Fallback University",
        "custom_field": "fallback",
    }


def test_map_clean_payload_to_template_handles_empty_clean_payload_with_name_default_and_slug_rule() -> None:
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        {},
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_empty_clean_payload_with_boolean_rule_and_unknown_default() -> None:
    template_columns = [
        {"name": "sponsored", "order": 1},
        {"name": "custom_field", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        {},
        template_columns=template_columns,
        defaults={"custom_field": "fallback"},
    )

    assert mapped == {
        "sponsored": False,
        "custom_field": "fallback",
    }


def test_map_clean_payload_to_template_handles_empty_clean_payload_with_name_default_website_default_and_slug_rule() -> None:
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "slug", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        {},
        template_columns=template_columns,
        defaults={"name": "Fallback University", "website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Fallback University",
        "website": "https://default.example.edu",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_empty_clean_payload_with_all_known_boolean_rules() -> None:
    template_columns = [
        {"name": "sponsored", "order": 1},
        {"name": "student_loan_available", "order": 2},
        {"name": "housing_availability", "order": 3},
        {"name": "immigration_support", "order": 4},
    ]

    mapped = map_clean_payload_to_template({}, template_columns=template_columns)

    assert mapped == {
        "sponsored": False,
        "student_loan_available": False,
        "housing_availability": False,
        "immigration_support": False,
    }


def test_map_clean_payload_to_template_handles_default_name_and_existing_website() -> None:
    clean_payload = {
        "name": None,
        "website": "https://real.example.edu",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "slug", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Fallback University",
        "website": "https://real.example.edu",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_default_name_and_existing_slug() -> None:
    clean_payload = {
        "name": None,
        "slug": "existing-slug",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "existing-slug",
    }


def test_map_clean_payload_to_template_handles_default_name_and_blank_slug() -> None:
    clean_payload = {
        "name": None,
        "slug": " ",
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_default_name_and_none_slug() -> None:
    clean_payload = {
        "name": None,
        "slug": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_default_name_and_blank_slug_default_overrides_rule() -> None:
    clean_payload = {
        "name": None,
        "slug": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "slug", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "slug": "chosen-slug"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "chosen-slug",
    }


def test_map_clean_payload_to_template_handles_missing_name_with_website_default_no_slug() -> None:
    clean_payload = {}
    template_columns = [
        {"name": "website", "order": 1},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "website": "https://default.example.edu",
    }


def test_map_clean_payload_to_template_handles_blank_name_with_website_default_and_no_slug() -> None:
    clean_payload = {
        "name": "",
        "website": None,
    }
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": None,
        "website": "https://default.example.edu",
    }


def test_map_clean_payload_to_template_handles_missing_everything_and_unknown_default_only() -> None:
    mapped = map_clean_payload_to_template(
        {},
        template_columns=[{"name": "custom_field", "order": 1}],
        defaults={"custom_field": "fallback"},
    )

    assert mapped == {
        "custom_field": "fallback",
    }


def test_map_clean_payload_to_template_handles_missing_everything_and_slug_default_only() -> None:
    mapped = map_clean_payload_to_template(
        {},
        template_columns=[{"name": "slug", "order": 1}],
        defaults={"slug": "fallback-slug"},
    )

    assert mapped == {
        "slug": "fallback-slug",
    }


def test_map_clean_payload_to_template_handles_missing_everything_and_slug_rule_only() -> None:
    mapped = map_clean_payload_to_template({}, template_columns=[{"name": "slug", "order": 1}])

    assert mapped == {
        "slug": None,
    }


def test_map_clean_payload_to_template_handles_missing_everything_and_name_default_only() -> None:
    mapped = map_clean_payload_to_template(
        {},
        template_columns=[{"name": "name", "order": 1}],
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
    }


def test_map_clean_payload_to_template_handles_missing_everything_and_name_default_plus_slug_column() -> None:
    mapped = map_clean_payload_to_template(
        {},
        template_columns=[{"name": "name", "order": 1}, {"name": "slug", "order": 2}],
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_existing_name_none_and_slug_column_first() -> None:
    clean_payload = {"name": None}
    template_columns = [{"name": "slug", "order": 1}, {"name": "name", "order": 2}]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "slug": None,
        "name": None,
    }


def test_map_clean_payload_to_template_handles_existing_name_default_and_slug_column_first() -> None:
    clean_payload = {"name": None}
    template_columns = [{"name": "slug", "order": 1}, {"name": "name", "order": 2}]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "slug": None,
        "name": "Fallback University",
    }


def test_map_clean_payload_to_template_handles_existing_name_default_and_slug_column_after() -> None:
    clean_payload = {"name": None}
    template_columns = [{"name": "name", "order": 1}, {"name": "slug", "order": 2}]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_existing_blank_name_default_and_slug_column_after() -> None:
    clean_payload = {"name": ""}
    template_columns = [{"name": "name", "order": 1}, {"name": "slug", "order": 2}]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_existing_blank_name_no_default_and_slug_column_after() -> None:
    clean_payload = {"name": ""}
    template_columns = [{"name": "name", "order": 1}, {"name": "slug", "order": 2}]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "slug": None,
    }


def test_map_clean_payload_to_template_handles_existing_blank_name_no_default_and_boolean_rule() -> None:
    clean_payload = {"name": ""}
    template_columns = [{"name": "name", "order": 1}, {"name": "sponsored", "order": 2}]

    mapped = map_clean_payload_to_template(clean_payload, template_columns=template_columns)

    assert mapped == {
        "name": None,
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_existing_blank_name_default_and_boolean_rule() -> None:
    clean_payload = {"name": ""}
    template_columns = [{"name": "name", "order": 1}, {"name": "sponsored", "order": 2}]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University"},
    )

    assert mapped == {
        "name": "Fallback University",
        "sponsored": False,
    }


def test_map_clean_payload_to_template_handles_existing_blank_name_default_and_website_default_and_slug() -> None:
    clean_payload = {"name": "", "website": None}
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "website", "order": 2},
        {"name": "slug", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "website": "https://default.example.edu"},
    )

    assert mapped == {
        "name": "Fallback University",
        "website": "https://default.example.edu",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_existing_blank_name_default_and_slug_default_value() -> None:
    clean_payload = {"name": "", "slug": None}
    template_columns = [{"name": "name", "order": 1}, {"name": "slug", "order": 2}]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "slug": "preferred-slug"},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "preferred-slug",
    }


def test_map_clean_payload_to_template_handles_existing_blank_name_default_and_slug_default_blank() -> None:
    clean_payload = {"name": "", "slug": None}
    template_columns = [{"name": "name", "order": 1}, {"name": "slug", "order": 2}]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "slug": ""},
    )

    assert mapped == {
        "name": "Fallback University",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_existing_blank_name_default_and_unknown_default() -> None:
    clean_payload = {"name": "", "custom_field": None}
    template_columns = [{"name": "name", "order": 1}, {"name": "custom_field", "order": 2}]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "custom_field": "fallback"},
    )

    assert mapped == {
        "name": "Fallback University",
        "custom_field": "fallback",
    }


def test_map_clean_payload_to_template_handles_existing_blank_name_default_unknown_default_and_slug() -> None:
    clean_payload = {"name": "", "custom_field": None}
    template_columns = [
        {"name": "name", "order": 1},
        {"name": "custom_field", "order": 2},
        {"name": "slug", "order": 3},
    ]

    mapped = map_clean_payload_to_template(
        clean_payload,
        template_columns=template_columns,
        defaults={"name": "Fallback University", "custom_field": "fallback"},
    )

    assert mapped == {
        "name": "Fallback University",
        "custom_field": "fallback",
        "slug": "fallback-university",
    }


def test_map_clean_payload_to_template_handles_minimal_noop_case() -> None:
    mapped = map_clean_payload_to_template({}, template_columns=[])

    assert mapped == {}
