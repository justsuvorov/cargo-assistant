import json
from pathlib import Path

import yaml
from hamcrest import assert_that, contains_string, equal_to, has_items

root = Path(__file__).parents[2]
pod = "spec.template.spec.containers.0"


def documents() -> tuple[str, ...]:
    return tuple(
        json.dumps(document)
        for path in sorted((root / "deploy/k8s").glob("*.yaml"))
        if path.name != "secret.yaml"
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if document
    )


def found(kind: str, name: str) -> str:
    return next(
        text
        for text in documents()
        if json.loads(text)["kind"] == kind and name in ("", json.loads(text)["metadata"]["name"])
    )


def node(kind: str, name: str, path: str) -> str:
    current = json.loads(found(kind, name))
    for step in path.split("."):
        current = current[int(step) if step.isdigit() else step]
    return json.dumps(current)


class Manifests:
    """Release files of the repository, asked about as one set of Kubernetes objects."""

    def kinds(self) -> frozenset[str]:
        return frozenset(str(json.loads(text)["kind"]) for text in documents())

    def value(self, kind: str, name: str, path: str) -> str:
        return str(json.loads(node(kind, name, path)))

    def names(self, kind: str, name: str, path: str) -> tuple[str, ...]:
        return tuple(str(key) for key in json.loads(node(kind, name, path)))

    def text(self, path: str) -> str:
        return (root / path).read_text(encoding="utf-8")


manifests = Manifests()


def test_describes_every_kind_the_contour_needs() -> None:
    assert_that(
        manifests.kinds(),
        equal_to(
            {
                "Namespace",
                "ConfigMap",
                "Secret",
                "PersistentVolumeClaim",
                "Job",
                "Deployment",
                "Service",
                "Ingress",
            }
        ),
        "Manifests do not cover every kind the contour needs",
    )


def test_puts_every_namespaced_object_into_the_namespace() -> None:
    assert_that(
        {
            manifests.value(kind, name, "metadata.namespace")
            for kind, name in (
                ("ConfigMap", "cargo-config"),
                ("Secret", "cargo-secret"),
                ("PersistentVolumeClaim", "cargo-storage"),
                ("Job", "cargo-migrate"),
                ("Deployment", "cargo-api"),
                ("Deployment", "cargo-worker"),
                ("Service", "cargo-api"),
                ("Ingress", "cargo-api"),
            )
        },
        equal_to({manifests.value("Namespace", "", "metadata.name")}),
        "Some object is not placed into the namespace of the application",
    )


def test_leaves_all_values_of_secret_example_empty() -> None:
    assert_that(
        {
            manifests.value("Secret", "", f"stringData.{key}")
            for key in manifests.names("Secret", "", "stringData")
        },
        equal_to({""}),
        "Secret example does not stay empty",
    )


def test_keeps_gateway_key_and_database_address_in_secret() -> None:
    assert_that(
        manifests.names("Secret", "", "stringData"),
        has_items("LLM_API_KEY", "DATABASE_URL"),
        "Gateway key and database address are not in the secret",
    )


def test_keeps_gateway_settings_in_config() -> None:
    assert_that(
        manifests.names("ConfigMap", "", "data"),
        has_items("LLM_PROVIDER", "LLM_API_URL", "LLM_MODEL", "LLM_CA_BUNDLE"),
        "Gateway settings are not in the config",
    )


def test_keeps_secrets_out_of_config() -> None:
    names = manifests.names("ConfigMap", "", "data")
    assert_that(
        ("LLM_API_KEY" in names, "DATABASE_URL" in names),
        equal_to((False, False)),
        "Gateway key or database address is not kept out of the config",
    )


def test_disables_login_and_trusts_forwarded_headers_by_config() -> None:
    assert_that(
        (
            manifests.value("ConfigMap", "", "data.AUTH_DISABLED"),
            "FORWARDED_ALLOW_IPS" in manifests.names("ConfigMap", "", "data"),
        ),
        equal_to(("true", True)),
        "Config does not disable login or does not set trust to forwarded headers",
    )


def test_shares_storage_between_pods_by_volume_with_many_writers() -> None:
    assert_that(
        manifests.names("PersistentVolumeClaim", "", "spec.accessModes"),
        equal_to(("ReadWriteMany",)),
        "Storage volume is not shared by many pods",
    )


def test_runs_api_and_worker_from_one_image() -> None:
    assert_that(
        manifests.value("Deployment", "cargo-api", f"{pod}.image"),
        equal_to(manifests.value("Deployment", "cargo-worker", f"{pod}.image")),
        "Api and worker do not run from one image",
    )


def test_checks_health_of_api_by_both_probes() -> None:
    assert_that(
        (
            manifests.value("Deployment", "cargo-api", f"{pod}.readinessProbe.httpGet.path"),
            manifests.value("Deployment", "cargo-api", f"{pod}.livenessProbe.httpGet.path"),
        ),
        equal_to(("/health", "/health")),
        "Api is not checked by health probes",
    )


def test_migrates_database_in_a_job_before_deployments_start() -> None:
    assert_that(
        manifests.names("Job", "", "spec.template.spec.containers.0.command"),
        equal_to(("alembic", "upgrade", "head")),
        "Migration job does not upgrade the database",
    )


def test_starts_worker_by_its_module() -> None:
    assert_that(
        manifests.names("Deployment", "cargo-worker", f"{pod}.command"),
        equal_to(("python", "-m", "app.jobs")),
        "Worker is not started by its module",
    )


def test_excludes_client_documents_and_secrets_from_image() -> None:
    assert_that(
        manifests.text(".dockerignore").splitlines(),
        has_items("data", "storage", ".env", "*.zip", "docs/eval", "tests"),
        "Image is not protected from client documents and secrets",
    )


def test_runs_image_as_user_without_privileges() -> None:
    assert_that(
        manifests.text("Dockerfile"),
        contains_string("USER cargo"),
        "Image does not drop privileges",
    )


def test_builds_image_with_short_commit_hash_as_version_and_tag() -> None:
    script = manifests.text("deploy/build-image.sh")
    assert_that(
        (
            "git rev-parse --short HEAD" in script,
            "APP_VERSION=${VERSION}" in script,
            "-t " in script,
        ),
        equal_to((True, True, True)),
        "Build script does not pass the short commit hash as version and tag",
    )
