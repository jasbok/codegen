/*
@@!.codegen.generated
*/

$$.source.includes.internal {{
#include "$$"
}}
$$.source.includes.external {{
#include <$$>
}}

$$.namespace{{
namespace $$
{
}}
// Default Constructor
$$.class.name::$$.class.name()
:   $$.class.fields.private[[:-1]]{{
        !!.class.private.prefix$$.name(),
    }}
    $$.class.fields.private[[-1]]{{
        !!.class.private.prefix$$.name()
    }}
{}

// Copy Constructor
$$.class.name::$$.class.name(const $$.class.name& copy)
:   $$.class.fields.private[[:-1]]{{
        !!.class.private.prefix$$.name(copy.!!.class.private.prefix$$.name),
    }}
    $$.class.fields.private[[-1]]{{
        !!.class.private.prefix$$.name(copy.!!.class.private.prefix$$.name)
    }}
{}

// Move Constructor
$$.class.name::$$.class.name($$.class.name&& move)
:   $$.class.fields.private[[:-1]]{{
        !!.class.private.prefix$$.name(std::move(move.!!.class.private.prefix$$.name)),
    }}
    $$.class.fields.private[[-1]]{{
        !!.class.private.prefix$$.name(std::move(move.!!.class.private.prefix$$.name))
    }}
{}

// Copy Assignment
$$.class.name& $$.class.name::operator=(const $$.class.name& copy){
    $$.class.fields.private {{
        !!.class.private.prefix$$.name = copy.!!.class.private.prefix$$.name;
    }}
    return *this;
}

// Move Assignment
$$.class.name& $$.class.name::operator=($$.class.name&& move){
    $$.class.fields.private {{
        !!.class.private.prefix$$.name = std::move(move.!!.class.private.prefix$$.name);
    }}
    return *this;
}

//
// Getters and Setters (Copy and Move)
//
$$.class.fields.private {{
    $$.type !!.class.name::$$.name(){
        return !!.class.private.prefix$$.name;
    }
    !!.class.name& !!.class.name::$$.name(const $$.type& $$.name){
        !!.class.private.prefix$$.name = $$.name;
        return *this;
    }
    !!.class.name& !!.class.name::$$.name($$.type&& $$.name){
        !!.class.private.prefix$$.name = std::move($$.name);
        return *this;
    }

}}

//
// Basic to Json function using crazy codegen templating.
// Note that this function will produce an extra comma for the last field.
//
std::string $$.class.name::json_crazy(){
    std::stringstream json;
    json << "{";
    $$.class.fields.private{{
        json << "\"$$.name\":" << $$.json.type[["boolean","number","bool","int","float","double"]]{{
                                      !!.class.private.prefix$$.name << ",";
                                  }}
                                  [["char","string"]]{{
                                      "\"" << !!.class.private.prefix$$.name << "\",";
                                  }}
                                  [["object"]]{{
                                      !!.class.private.prefix$$.name...json() << ",";
                                  }}
                                  [["array"]]{{
                                      "[";
                                      int i = 0;
                                      for(auto item : !!.class.private.prefix^^.^^.name){
                                          ^^.subtype[["boolean","number","bool","int","float","double"]]{{
                                              json << item;
                                          }}
                                          [["char","string"]]{{
                                              json << "\"" << item << "\"";
                                          }}
                                          [["object"]]{{
                                              json << item.json();
                                          }}
                                          if(++i < !!.class.private.prefix^^.^^.name...size()){
                                              json << ",";
                                          }
                                      }
                                      json << "],";
                                  }}
                                  [["map"]]{{
                                      "{";
                                      int i = 0;
                                      for(auto item : !!.class.private.prefix^^.^^.name){
                                          json <<
                                          ^^.subtype[["boolean","number","bool","int","float","double"]]{{
                                              json << "\"" << item.first << "\":" << item.second;
                                          }}
                                          [["char","string"]]{{
                                              json << "\"" << item.first << "\": \"" << item.second << "\"";
                                          }}
                                          [["object"]]{{
                                              json << "\"" << item.first << "\":" << item.second.json();
                                          }}
                                          if(++i < !!.class.private.prefix^^.^^.name...size()){
                                              json << ",";
                                          }
                                      }
                                      json << "},";
                                  }}
    }}
    json << "}";
    return json.str();
}

//
// Basic to Json function using sane C++ functions/templates in combination with
// codegen templating.
//
std::string $$.class.name::json_sane(){
    std::stringstream json;
    json << "{";
    $$.class.fields.private[[:-1]]{{
        json << "\"$$.name\":" << to_json(!!.class.private.prefix^^.^^.name) << ","
    }}
    $$.class.fields.private[[-1]]{{
        json << "\"$$.name\":" << to_json(!!.class.private.prefix^^.^^.name)
    }}
    json << "}";
    return json.str();
}

$$.namespace{{}}}
