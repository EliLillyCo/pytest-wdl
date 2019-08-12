import "submodule.wdl"

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
  Int in_int

  call cat {
    input: in_txt = in_txt
  }

  call submodule.foo {
    input:
      s = "foo"
  }

  output {
    File out_txt = cat.out_txt
    File out2 = foo.out
    Int out_int = in_int
  }
}
