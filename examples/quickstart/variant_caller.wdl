version 1.0

struct Reference {
  File fasta
  String organism
}

workflow call_variants {
  input {
    File bam
    Reference ref
  }

  call freebayes {
    input:
      bam=bam,
      ref=ref
  }

  output {
    File vcf = freebayes.vcf
  }
}

task freebayes {
  input {
    File bam
    Reference ref
  }

  String prefix = basename(bam, ".bam")

  command <<<
  freebayes -v '~{prefix}.vcf.gz' --strict-vcf -f ~{ref.fasta} ~{bam}
  >>>

  runtime {
    docker: "quay.io/biocontainers/freebayes:1.3.2--py36hc088bd4_0"
  }

  output {
    File vcf = "${prefix}.vcf.gz"
  }
}
