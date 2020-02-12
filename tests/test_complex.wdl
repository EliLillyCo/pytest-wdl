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
    Array[Pair[String, String]] array_pairs
    Array[Pair[String, Pair[String, String]]] array_pair_pair_string
  }

  Boolean default_fail = select_first([fail, false])

  scatter (each in array_pair_pair_string) {
    String first_level_key = each.left
    String second_level_key = each.right.left
    String second_level_val = each.right.right
  }

  scatter (each in array_pairs) {
    String key_string = each.left
    String val_string = each.right
  }

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
