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
    Pair[String, String] pair_string
    Array[Pair[String, String]] array_pair_string
    Array[Pair[String, Pair[String, String]]] array_pair_pair_string
  }

  scatter (each in array_pair_string) {
    String test_string_left = each.left
    String test_string_right = each.right
  }

  scatter (each in array_pair_pair_string) {
    String first_level_key = each.left
    String second_level_key = each.right.left
    String second_level_val = each.right.right
  }

  call test_task {
    input:
      str=str,
      array_str=array_str,
      map_str_str=map_str_str,
      struc=struc,
      array_struc=array_struc,
      map_str_struc=map_str_struc,
      pair_string=pair_string,
      array_pair_string=array_pair_string,
      array_pair_pair_string=array_pair_pair_string
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
    Pair[String, String] pair_string
    Array[Pair[String, String]] array_pair_string
    Array[Pair[String, Pair[String, String]]] array_pair_pair_string
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
