task foo {
  String s

  command <<<
  echo -e ${s} > output
  >>>

  output {
    File out = "output"
  }
}
