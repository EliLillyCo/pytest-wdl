task foo {
  String s

  command <<<
  echo -e ${s} > output
  >>>

  output {
    File out = "output"
  }
}

task foo_fail {
  String s

  command <<<
  echo -e ${s} > output
  exit 1
  >>>

  output {
    File out = "output"
  }
}