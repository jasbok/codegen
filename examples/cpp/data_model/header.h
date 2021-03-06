/*
@@!.codegen.generated
*/

#ifndef %%.str.upper{{$$.namespace.._$$.class.name.._h}}
#define %%.str.upper{{$$.namespace.._$$.class.name.._h}}

$$.header.includes.internal {{
#include "$$"
}}

$$.header.includes.external {{
#include <$$>
}}

$$.namespace {{
namespace $$
{
}}
class $$.class.name {
public:
    // Default Constructor
    $$.class.name();

    // Copy Constructor
    $$.class.name(const $$.class.name& copy);

    // Move Constructor
    $$.class.name($$.class.name&& move);

    // Copy Assignment
    $$.class.name& operator=(const $$.class.name& copy);

    // Move Assignment
    $$.class.name& operator=($$.class.name&& move);

    // Getters and Setters (Copy and Move)
    $$.class.fields.private {{
      $$.type $$.name();
      !!.class.name& $$.name(const $$.type& $$.name);
      !!.class.name& $$.name($$.type&& $$.name);

    }}

    std::string json();

    friend std::ostream& operator<< (std::ostream& cout, const $$.class.name& %%.str.lower{{$$.class.name}}) {
            cout << json();
            return cout;
    }

private:
    $$.class.fields.private {{
        $$.type !!.class.private.prefix$$.name;
    }}
};
$$.namespace {{
}
}}

#endif // %%.str.upper{{$$.namespace.._$$.class.name.._h}}
