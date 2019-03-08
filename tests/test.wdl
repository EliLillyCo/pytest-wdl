task cat {
  File in_txt

  command <<<
    cat ${in_txt} > out.txt
  >>>

  runtime {
    docker: "frolvlad/alpine-bash"
  }

  output {
    File out_txt = "out.txt"
  }
}

workflow cat_file {
  File in_txt

  call cat {
    input: in_txt = in_txt
  }

  output {
    File out_txt = cat.out_txt
  }
}