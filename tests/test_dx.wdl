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
  }
}