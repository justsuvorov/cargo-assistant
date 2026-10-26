from hamcrest import assert_that, equal_to

from app.jobs.models import Base


def test_declares_all_tables_of_the_data_model() -> None:
    assert_that(
        set(Base.metadata.tables),
        equal_to(
            {
                "policies",
                "policy_documents",
                "policy_profiles",
                "declarations",
                "check_results",
                "rule_sets",
                "jobs",
                "eval_runs",
                "llm_calls",
            }
        ),
        "Data model does not declare the nine tables",
    )
