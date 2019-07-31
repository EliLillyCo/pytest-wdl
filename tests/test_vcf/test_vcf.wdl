task nothing {
   File vcf

   command <<<
   mv ${vcf} new_filename.bam
   >>>
   runtime {
       docker: "debian:stretch-slim"
   }
   output {
       File output_vcf = "new_filename.bam"
   }
}

workflow test_vcf {
    File vcf

    call nothing {
        input:
            vcf=vcf
    }

    output {
        File output_vcf = nothing.output_vcf
    }
}
