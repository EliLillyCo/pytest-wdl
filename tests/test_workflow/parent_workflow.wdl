version 1.0

import "hello_world.wdl" as hello_world

workflow hello_world_workflow {
  input {
    Array[File] input_files
  }

  scatter (file in input_files) {
    call hello_world.hello_world {
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
