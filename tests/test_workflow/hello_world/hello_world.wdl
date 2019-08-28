version 1.0


### Take a file and a string and output a file.

task hello_world {
  input {
    File input_file
    String output_filename
  }

  parameter_meta {
    input_file: {description: "Provide a small input file."}
    output_filename: {description: "Specify the output filename."}
  }

  command <<<
  set -exo pipefail

  >&2 echo "Renaming this input file ~{input_file} to ~{output_filename}"

  mv ~{input_file} ~{output_filename}
  >>>

  runtime {
    docker: "debian:stretch-slim"
  }

  output {
    File output_file = "${output_filename}"
  }

}
