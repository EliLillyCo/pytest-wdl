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
    Float? min_alternate_fraction
  }

  String prefix = basename(bam, ".bam")
  Float default_min_alternate_fraction = select_first([min_alternate_fraction, 0.2])

  command <<<
  freebayes -v '~{prefix}.vcf' -f ~{ref.fasta} \
    -F ~{default_min_alternate_fraction} \
    ~{bam}
  >>>

  runtime {
    docker: "quay.io/biocontainers/freebayes:1.3.2--py36hc088bd4_0"
  }

  output {
    File vcf = "${prefix}.vcf"
  }
}
