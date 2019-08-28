version 1.0

import "hello_world.wdl" as hello_world

workflow test_hello_world {
  input {
    File input_file
    String output_filename
  }

  call hello_world.hello_world {
    input:
      input_file=input_file,
      output_filename=output_filename
  }
  output {
    File output_file = hello_world.output_file
  }
}
