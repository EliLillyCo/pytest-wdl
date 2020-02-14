def test_variant_caller(workflow_data, workflow_runner):
    inputs = {
        "bam": workflow_data["bam"],
        "ref": {
            "fasta": workflow_data["reference_fa"],
            "organism": "human"
        }
    }
    expected = workflow_data.get_dict("vcf")
    workflow_runner(
        "variant_caller.wdl",
        inputs,
        expected
    )
