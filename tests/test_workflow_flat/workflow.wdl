version 1.0

workflow hello_world_workflow {
  input {
    Array[File] input_files
  }

  scatter (file in input_files) {
    call hello_world {
      input:
        input_file=file,
        output_filename=basename(file) + ".renamed"
    }
  }

  output {
    Array[File] renamed_files = hello_world.output_file
    File single_file = renamed_files[0]
  }
}

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

