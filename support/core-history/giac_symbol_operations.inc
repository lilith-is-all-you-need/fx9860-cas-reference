  struct SymbolTransaction::Change {
    sym_string_tab::iterator position;
    Change *next;
    Change() noexcept : next(nullptr) {}
  };

  static_assert(std::is_nothrow_destructible<gen>::value,
                "Symbol rollback requires non-throwing gen destruction");
  static_assert(std::is_nothrow_destructible<std::string>::value,
                "Symbol rollback requires non-throwing name destruction");

  SymbolTransaction *SymbolTransaction::current_=nullptr;

  SymbolTransaction::SymbolTransaction() noexcept
    : previous_(current_), table_(nullptr), changes_(nullptr),
      global_initialisation_(nullptr), previous_initialisation_(0),
      committed_(false) {
    current_=this;
  }

  SymbolTransaction::~SymbolTransaction() noexcept {
    current_=previous_;
    if (committed_ && previous_) {
      if (changes_) {
        Change *tail=changes_;
        while (tail->next) tail=tail->next;
        tail->next=previous_->changes_;
        previous_->changes_=changes_;
        previous_->table_=table_;
      }
      if (global_initialisation_ && !previous_->global_initialisation_) {
        previous_->global_initialisation_=global_initialisation_;
        previous_->previous_initialisation_=previous_initialisation_;
      }
      return;
    }
    while (changes_) {
      Change *change=changes_;
      changes_=change->next;
      // erase(iterator) rebalances and destroys a node; it does not compare
      // keys or allocate. All candidate/heap owners have already died.
      if (!committed_) table_->erase(change->position);
      delete change;
    }
    if (!committed_ && global_initialisation_)
      *global_initialisation_=previous_initialisation_;
  }

  void SymbolTransaction::commit() noexcept {
    committed_=true;
  }

  void SymbolTransaction::record_global_initialisation(int &flag) noexcept {
    if (current_ && !current_->global_initialisation_) {
      current_->global_initialisation_=&flag;
      current_->previous_initialisation_=flag;
    }
  }

  void SymbolTransaction::insert(const std::string &name, const gen &value) {
    sym_string_tab &table=syms();
    if (table.find(name)!=table.end()) return;
    SymbolTransaction *transaction=current_;
    // Reserve the undo node before modifying the map. All later allocation
    // failures leave either no map entry or a fully journalled entry.
    std::unique_ptr<Change> change(transaction ? new Change : nullptr);
    const auto inserted=table.insert(std::make_pair(name,value));
    if (inserted.second && change) {
      change->position=inserted.first;
      change->next=transaction->changes_;
      transaction->table_=&table;
      transaction->changes_=change.release();
    }
  }
