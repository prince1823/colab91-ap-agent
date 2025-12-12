"""Execute taxonomy and company context updates."""

from typing import Dict

from core.hitl.yaml_service import read_taxonomy_yaml, update_taxonomy


def execute_company_context_change(dataset_name: str, action_details: Dict) -> None:
    """
    Execute a company context update.

    Args:
        dataset_name: Dataset name
        action_details: Dictionary with field_name, current_value, proposed_value

    Raises:
        FileNotFoundError: If taxonomy file doesn't exist
    """
    field_name = action_details['field_name']
    proposed_value = action_details['proposed_value']

    # Update the taxonomy YAML
    update_taxonomy(
        dataset_name=dataset_name,
        change_type="company_context",
        updates={field_name: proposed_value}
    )


def execute_taxonomy_description_change(dataset_name: str, action_details: Dict) -> None:
    """
    Execute a taxonomy description update.

    Args:
        dataset_name: Dataset name
        action_details: Dictionary with taxonomy_path, current_description, proposed_description

    Raises:
        FileNotFoundError: If taxonomy file doesn't exist
    """
    taxonomy_path = action_details['taxonomy_path']
    proposed_description = action_details['proposed_description']

    # Update the taxonomy YAML
    update_taxonomy(
        dataset_name=dataset_name,
        change_type="taxonomy_description",
        updates={taxonomy_path: proposed_description}
    )
