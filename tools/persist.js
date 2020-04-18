function insertBatch(collection, documents) {
  var bulkInsert = collection.initializeUnorderedBulkOp();
  var insertedIds = [];
  var id;
  documents.forEach(function(doc) {
    id = doc._id;
    // Insert without raising an error for duplicates
    bulkInsert.find({_id: id}).upsert().replaceOne(doc);
    insertedIds.push(id);
  });
  bulkInsert.execute();
  return insertedIds;
}

function deleteBatch(collection, documents) {
  var bulkRemove = collection.initializeUnorderedBulkOp();
  documents.forEach(function(doc) {
    bulkRemove.find({_id: doc._id}).removeOne();
  });
  bulkRemove.execute();
}

function moveDocuments(sourceCollection, targetCollection, filter, batchSize) {
  print("Moving " + sourceCollection.find(filter).count() + " documents from " + sourceCollection + " to " + targetCollection);
  var count;
  while ((count = sourceCollection.find(filter).count()) > 0) {
    print(count + " documents remaining");
    sourceDocs = sourceCollection.find(filter).limit(batchSize);
    idsOfCopiedDocs = insertBatch(targetCollection, sourceDocs);

    targetDocs = targetCollection.find({_id: {$in: idsOfCopiedDocs}});
    deleteBatch(sourceCollection, targetDocs);
  }
  print("Done!")
}

memory = connect("localhost:27017/express");
hard = connect("localhost:27020/express");


moveDocuments(memory.locations, hard.locations, {}, 100);
quit();
