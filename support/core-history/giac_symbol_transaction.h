#ifndef KHICAS_GIAC_SYMBOL_TRANSACTION_H
#define KHICAS_GIAC_SYMBOL_TRANSACTION_H

#include "gen.h"
#include "global.h"
#include <memory>
#include <type_traits>

namespace giac {

// The bridge declares this before HeapTransaction and candidate/context
// owners, so every borrowed id_name key dies before a new intern is erased.
class SymbolTransaction {
public:
    SymbolTransaction() noexcept;
    ~SymbolTransaction() noexcept;
    SymbolTransaction(const SymbolTransaction &) = delete;
    SymbolTransaction &operator=(const SymbolTransaction &) = delete;

    void commit() noexcept;
    static void insert(const std::string &name, const gen &value);
    // Only a stable process-global field may be recorded here. A candidate
    // context is destroyed before this transaction and cannot supply a field.
    static void record_global_initialisation(int &flag) noexcept;

private:
    struct Change;
    static SymbolTransaction *current_;
    SymbolTransaction *previous_;
    sym_string_tab *table_;
    Change *changes_;
    int *global_initialisation_;
    int previous_initialisation_;
    bool committed_;
};

}

#endif
