"""Run from the source root: python -m examples.inspect_project."""
from pathlib import Path
from electrochem.archive import load
from electrochem.models import energy_gate


if __name__ == "__main__":
    project, blobs = load(Path(__file__).with_name("synthetic.ecproj"))
    print("Project:", project.id)
    print("Source payloads verified:", len(blobs))
    print("Raw rows / normalized observations:", len(project.raw_rows), len(project.observations))
    print("Scientific input digest:", project.input_digest())
    print("Energy eligibility:", energy_gate(project, "interval"))
    print("The demonstration preserves unresolved Ewe; it does not calculate energy.")
