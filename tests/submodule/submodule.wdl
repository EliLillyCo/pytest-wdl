version 1.0

task foo {
  input {
    String s
  }

  command <<<
  echo -e ~{s} > output
  >>>

  runtime {
    docker: "frolvlad/alpine-bash:latest"
  }

  output {
    File out = "output"
  }
}

task foo_fail {
  input {
    String s
  }

  command <<<
  echo -e ~{s} > output
  exit 1
  >>>

  runtime {
    docker: "frolvlad/alpine-bash:latest"
  }

  output {
    File out = "output"
  }
}