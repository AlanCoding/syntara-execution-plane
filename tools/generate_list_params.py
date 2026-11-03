#!/usr/bin/env python3
"""Generate client list params base classes from execution plane models.

This script reads __sortable_fields__ from the execution plane models and generates
base classes for the client list params with proper Field definitions and Literal sort types.
"""

import sys
from pathlib import Path
from textwrap import dedent, indent

# Add src to path so we can import execution_plane
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from execution_plane.models.cluster import Cluster
from execution_plane.models.execution_target import ExecutionTarget


def generate_sort_literal(model_name: str, sortable_fields: list[str], default_sort: str, description: str) -> str:
    """Generate the Literal type for sort field with both positive and negative versions."""
    sort_options = []
    for field in sortable_fields:
        sort_options.append(f'        "{field}",')
        sort_options.append(f'        "-{field}",')

    sort_literal = "\n".join(sort_options)
    return f"""    sort: Literal[
{sort_literal}
    ] = Field(default="{default_sort}", description="{description}")"""


def get_supported_operators(field_name: str, model_class) -> str:
    """Determine supported operators for a field based on its type."""
    from datetime import datetime

    from execution_plane.query_filters import column_python_type, query_column

    python_type = None

    # Try to get type from SQLAlchemy column
    try:
        column = query_column(model_class, field_name)
        python_type = column_python_type(column)
    except (AttributeError, KeyError):
        pass

    # Fallback to pydantic field annotation if column type is None
    if python_type is None:
        model_field = model_class.model_fields.get(field_name)
        if model_field and model_field.annotation:
            # Extract the actual type from Optional/Union if present
            import typing

            annotation = model_field.annotation
            # Handle Optional[T] which is Union[T, None]
            if hasattr(typing, "get_args") and typing.get_args(annotation):
                args = typing.get_args(annotation)
                # Filter out NoneType
                non_none_types = [arg for arg in args if arg is not type(None)]
                if non_none_types:
                    python_type = non_none_types[0]
            else:
                python_type = annotation

    # Boolean fields
    if python_type is bool:
        return "eq, in, and isnull"

    # String fields
    if python_type is str:
        return "eq, in, contains, and starts_with"

    # Datetime fields
    if python_type is datetime:
        return "eq, in, gt, gte, lt, lte, and isnull"

    # UUID and enum fields (default)
    return "eq and in"


def generate_filter_fields(model_class, model_name: str, short_name: str | None = None) -> list[str]:
    """Generate Field definitions for filterable fields based on the model."""
    filterable = getattr(model_class, "__filterable_fields__", [])
    field_defs = []

    for field_name in filterable:
        # Get the description from the model field
        model_field = model_class.model_fields.get(field_name)
        if model_field and model_field.description:
            base_description = model_field.description
        else:
            base_description = f"{field_name} field"

        # Add operator support info
        operators = get_supported_operators(field_name, model_class)

        # Special case for id fields to mention membership syntax
        if field_name == "id":
            full_description = f"{base_description}; id[in]=uuid1,uuid2 for membership"
        elif field_name == "cluster_id":
            full_description = f"{base_description}; supports {operators}"
        else:
            full_description = f"{base_description}; supports {operators}"

        # Format field definition, breaking long lines
        one_line = f'    {field_name}: str | None = Field(default=None, description="{full_description}")'
        if len(one_line) <= 120:
            field_def = one_line
        else:
            # Check if breaking at description still exceeds 120
            desc_line = f'        default=None, description="{full_description}"'
            if len(desc_line) <= 120:
                field_def = f'    {field_name}: str | None = Field(\n{desc_line}\n    )'
            else:
                # Need to break the description itself
                field_def = f'    {field_name}: str | None = Field(\n        default=None,\n        description="{full_description}",\n    )'
        field_defs.append(field_def)

    return field_defs


def generate_base_class(
    model_class,
    class_name: str,
    model_name: str,
    default_sort: str,
    sort_description: str,
    short_name: str | None = None,
) -> str:
    """Generate a complete base class for list params."""
    sortable = getattr(model_class, "__sortable_fields__", [])
    filter_fields = generate_filter_fields(model_class, model_name, short_name)
    sort_literal = generate_sort_literal(model_name, sortable, default_sort, sort_description)

    filter_fields_str = "\n".join(filter_fields)

    return f'''class {class_name}(EPListParams):
    """Generated base for {model_name} list params with filter fields and sort options."""

{filter_fields_str}
{sort_literal}'''


def main() -> None:
    """Generate the _generated_list_params.py module."""
    output_path = src_path / "execution_plane_client" / "models" / "_generated_list_params.py"

    cluster_base = generate_base_class(
        Cluster,
        "ClusterListParamsBase",
        "Cluster",
        "created_at",
        "Cluster sort field; oldest first by default.",
        short_name="Cluster",
    )

    target_base = generate_base_class(
        ExecutionTarget,
        "ExecutionTargetListParamsBase",
        "ExecutionTarget",
        "created_at",
        "Execution-target sort field; oldest first by default.",
        short_name="Target",
    )

    content = f'''"""Generated base classes for list params with sortable fields.

DO NOT EDIT: This file is auto-generated by tools/generate_list_params.py
Run 'make generate-list-params' to regenerate.
"""

from typing import Literal

from pydantic import Field

from execution_plane_client.models.shared import EPListParams


{cluster_base}


{target_base}
'''

    output_path.write_text(content)
    print(f"Generated {output_path}")


if __name__ == "__main__":
    main()
