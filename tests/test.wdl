version 1.0

import "submodule.wdl"

task cat {
  input {
    File in_txt
  }

  command <<<
    cat ~{in_txt} > out.txt
  >>>

  runtime {
    docker: "frolvlad/alpine-bash:latest"
  }

  output {
    File out_txt = "out.txt"
  }
}

workflow cat_file {
  input {
    File in_txt
    Int in_int
    Boolean? fail
  }

  Boolean default_fail = select_first([fail, false])

  call cat {
    input: in_txt = in_txt
  }

  if (default_fail) {
    call submodule.foo_fail {
      input:
        s = "foo"
    }
  }
  if (!default_fail) {
    call submodule.foo {
      input:
        s = "foo"
    }
  }

  File foo_out = select_first([foo_fail.out, foo.out])

  output {
    File out_txt = cat.out_txt
    File out2 = foo_out
    Int out_int = in_int
  }
}
