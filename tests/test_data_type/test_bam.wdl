task nothing {
   File bam

   command <<<
   mv ${bam} new_filename.bam
   >>>
   runtime {
       docker: "debian:stretch-slim"
   }
   output {
       File output_bam = "new_filename.bam"
   }
}

workflow test_bam {
    File bam

    call nothing {
        input:
            bam=bam
    }

    output {
        File output_bam = nothing.output_bam
    }
}
