version 1.0

struct TestStruct {
  String str
  Array[String] array_str
  Map[String, String] map_str_str
}

workflow test {
  input {
    String str
    Array[String] array_str
    Map[String, String] map_str_str
    TestStruct struc
    Array[TestStruct] array_struc
    Map[String, TestStruct] map_str_struc
    Pair[String, String] pair_str_str
    Array[Pair[String, String]] array_pair_str_str
  }

  call test_task {
    input:
      str=str,
      array_str=array_str,
      map_str_str=map_str_str,
      struc=struc,
      array_struc=array_struc,
      map_str_struc=map_str_struc
  }

  output {
    String str2 = str
  }
}

task test_task {
  input {
    String str
    Array[String] array_str
    Map[String, String] map_str_str
    TestStruct struc
    Array[TestStruct] array_struc
    Map[String, TestStruct] map_str_struc
  }

  command <<<
  >>>

  runtime {
    docker: "frolvlad/alpine-bash:latest"
  }

  output {
    String str_out = str
  }
}
