########### AGGREGATED COMPONENTS AND DEPENDENCIES FOR THE MULTI CONFIG #####################
#############################################################################################

set(bullet3_COMPONENT_NAMES "")
if(DEFINED bullet3_FIND_DEPENDENCY_NAMES)
  list(APPEND bullet3_FIND_DEPENDENCY_NAMES )
  list(REMOVE_DUPLICATES bullet3_FIND_DEPENDENCY_NAMES)
else()
  set(bullet3_FIND_DEPENDENCY_NAMES )
endif()

########### VARIABLES #######################################################################
#############################################################################################
set(bullet3_PACKAGE_FOLDER_RELEASE "C:/Users/kylin/.conan2/p/bulled9746efc5f47b/p")
set(bullet3_BUILD_MODULES_PATHS_RELEASE "${bullet3_PACKAGE_FOLDER_RELEASE}/lib/cmake/bullet/conan-official-bullet3-variables.cmake")


set(bullet3_INCLUDE_DIRS_RELEASE "${bullet3_PACKAGE_FOLDER_RELEASE}/include"
			"${bullet3_PACKAGE_FOLDER_RELEASE}/include/bullet")
set(bullet3_RES_DIRS_RELEASE )
set(bullet3_DEFINITIONS_RELEASE )
set(bullet3_SHARED_LINK_FLAGS_RELEASE )
set(bullet3_EXE_LINK_FLAGS_RELEASE )
set(bullet3_OBJECTS_RELEASE )
set(bullet3_COMPILE_DEFINITIONS_RELEASE )
set(bullet3_COMPILE_OPTIONS_C_RELEASE )
set(bullet3_COMPILE_OPTIONS_CXX_RELEASE )
set(bullet3_LIB_DIRS_RELEASE "${bullet3_PACKAGE_FOLDER_RELEASE}/lib")
set(bullet3_BIN_DIRS_RELEASE )
set(bullet3_LIBRARY_TYPE_RELEASE STATIC)
set(bullet3_IS_HOST_WINDOWS_RELEASE 1)
set(bullet3_LIBS_RELEASE Bullet3OpenCL_clew Bullet3Dynamics Bullet3Collision Bullet3Geometry Bullet2FileLoader BulletSoftBody BulletDynamics BulletCollision BulletInverseDynamics LinearMath Bullet3Common)
set(bullet3_SYSTEM_LIBS_RELEASE )
set(bullet3_FRAMEWORK_DIRS_RELEASE )
set(bullet3_FRAMEWORKS_RELEASE )
set(bullet3_BUILD_DIRS_RELEASE )
set(bullet3_NO_SONAME_MODE_RELEASE FALSE)


# COMPOUND VARIABLES
set(bullet3_COMPILE_OPTIONS_RELEASE
    "$<$<COMPILE_LANGUAGE:CXX>:${bullet3_COMPILE_OPTIONS_CXX_RELEASE}>"
    "$<$<COMPILE_LANGUAGE:C>:${bullet3_COMPILE_OPTIONS_C_RELEASE}>")
set(bullet3_LINKER_FLAGS_RELEASE
    "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,SHARED_LIBRARY>:${bullet3_SHARED_LINK_FLAGS_RELEASE}>"
    "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,MODULE_LIBRARY>:${bullet3_SHARED_LINK_FLAGS_RELEASE}>"
    "$<$<STREQUAL:$<TARGET_PROPERTY:TYPE>,EXECUTABLE>:${bullet3_EXE_LINK_FLAGS_RELEASE}>")


set(bullet3_COMPONENTS_RELEASE )