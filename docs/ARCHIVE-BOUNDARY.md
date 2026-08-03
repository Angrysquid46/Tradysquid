# Archive boundary

- Legacy commit: `ba75aae5f34f3889404bfe0c7c0b96663a92a657`
- Preserved branch: `archive/current-failed-implementation`
- Replacement branch: `clean-rebuild`

The replacement commit uses a newly constructed tree rather than modifying or importing the legacy application modules. The commit retains the old commit as its Git parent so GitHub can review the full deletion-and-replacement diff. The old source remains recoverable through the archive branch.

An annotated tag and local Windows backup remain blocked because those operations require capabilities not exposed through the connected GitHub interface or access to the production computer.
